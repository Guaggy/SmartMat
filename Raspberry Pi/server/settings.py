"""Analysis and alert settings, in layers: factory default (config.py and the built-in preset), then the site layer
(all mats), then the mat's own layer. A layer holds only what it overrides; an unset key falls back to the layer above.

Every change to a layer is a new, numbered version that is kept for good: who, when, why, what changed, and the full set
of overrides after it. A version can be rolled back (that is a new version again). The version in force when an alert
was raised is stamped on the alert (`stamp`), so it can always be traced which settings produced it.

Keys are flat: the server rules (`alert_high_hold_s`, `relief_minutes`, ...), the engineering preset of the desktop
app as `contact_threshold_kpa` and `temporal.*` / `hotspots.*` / `movement.*`, and `indices` (the whole list of risk
index definitions, or None = the built-in ones tuned by `relief_minutes` and `near_percent`).
Nothing here touches the mats directly: the server registers a listener that pushes the resolved values to the engines.
"""

import math
import threading
import time
from collections import namedtuple

import config
from processing.indices import validate_indices
from processing.settings import ENGINEERING_GROUPS, unflatten_preset

Spec = namedtuple("Spec", "key group type config_name fallback low high unit advanced site_only choices")

SITE = "site"
MISSING = object()


def _row(key, group, kind, config_name, fallback, low, high, unit, advanced=False, site_only=False):
    return Spec(key, group, kind, config_name, fallback, low, high, unit, advanced, site_only, None)


# the server rules; site_only ones belong to the whole installation, not to a mat
RULES = (
    _row("alert_high_hold_s", "alerts", "int", "ALERT_HIGH_HOLD_S", 30, 5, 3600, "s"),
    _row("alert_offline_s", "alerts", "int", "ALERT_OFFLINE_S", 30, 5, 3600, "s"),
    _row("push_enabled", "alerts", "bool", "PUSH_ENABLED", True, None, None, "", site_only=True),
    _row("relief_minutes", "risk", "int", "RISK_RELIEF_MIN", 120, 10, 720, "min"),
    _row("near_percent", "risk", "int", "RISK_NEAR_PERCENT", 80, 50, 99, "%"),
    _row("stale_after_s", "mats", "int", "STALE_AFTER_S", 10, 3, 300, "s"),
    _row("saturation_warn_cells", "mats", "int", "SATURATION_WARN_CELLS", 1, 1, 400, "", site_only=True),
    _row("posture_hold_s", "posture", "float", "POSTURE_HOLD_S", 3.0, 0, 60, "s", advanced=True),
    _row("posture_side_cells", "posture", "float", "POSTURE_SIDE_CELLS", 2.0, 0.5, 10, "cells", advanced=True),
    _row("posture_forward_cells", "posture", "float", "POSTURE_FORWARD_CELLS", 2.5, 0.5, 10, "cells", advanced=True),
    _row("retention_days", "data", "int", "RETENTION_DAYS", 30, 1, 365, "days", site_only=True),
)
INDICES = Spec("indices", "risk", "list", None, None, None, None, "", True, False, None)

_engineering = None   # cached: (specs, flat defaults); built from processing.settings.default_settings() once


def _engineering_specs():
    global _engineering
    if _engineering is None:
        from processing.settings import default_settings
        nested = default_settings()
        specs, defaults = [], {}
        flat = [("contact_threshold_kpa", "contact", nested["contact_threshold_kpa"])]
        for group in ENGINEERING_GROUPS:
            flat += [(f"{group}.{name}", group, value) for name, value in nested[group].items()]
        for key, group, value in flat:
            kind = "choice" if isinstance(value, str) else "int" if isinstance(value, int) and not isinstance(value, bool) else "float"
            choices = ("Full pressure", "Above threshold") if kind == "choice" else None
            unit = "kPa" if key.endswith("kpa") else "s" if key.endswith("_s") else ""
            specs.append(Spec(key, group, kind, None, value, None if kind == "choice" else 0, None, unit, True, False, choices))
            defaults[key] = value
        _engineering = (specs, defaults)
    return _engineering


def all_specs():
    return [*RULES, *_engineering_specs()[0], INDICES]


def spec_of(key):
    return next((spec for spec in all_specs() if spec.key == key), None)


def keys():
    return [spec.key for spec in all_specs()]


def _label(key):
    return key.replace("_", " ").replace(".", " ")


def _check(spec, value):
    """The value as its type, or ValueError with a sentence for the user"""
    name = _label(spec.key)
    if spec.type == "list":
        return validate_indices(value)
    if spec.type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be on or off")
        return value
    if spec.type == "choice":
        if value not in spec.choices:
            raise ValueError(f"{name} must be one of: {', '.join(spec.choices)}")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a number")
    if spec.type == "int":
        if value != int(value):
            raise ValueError(f"{name} must be a whole number")
        value = int(value)
    else:
        value = float(value)
    unit = " " + spec.unit if spec.unit else ""
    if spec.high is None:
        if value < spec.low:
            raise ValueError(f"{name} must be at least {spec.low:g}{unit}")
    elif not spec.low <= value <= spec.high:
        raise ValueError(f"{name} must be between {spec.low:g} and {spec.high:g}{unit}")
    return value


unflatten = unflatten_preset   # the engineering part of a flat dict as the nested preset of processing.settings


def _validate_resolved(flat):
    """The cross-checks of the desktop's presets (thresholds that must stay ordered), on a full resolved set"""
    from processing.settings import validate_settings
    validate_settings(unflatten(flat))


class Settings:
    def __init__(self, store=None, clock=time.time):
        self._store, self._clock = store, clock
        self._lock = threading.RLock()
        self._listeners = []
        self._layers = {SITE: {}}        # scope -> overrides
        self._versions = {SITE: 0}       # scope -> newest version (0 = nothing ever set)
        self._memory = {}                # scope -> [(version, t, user, reason, overrides, changes)] when there is no database
        if store is not None:
            current = store.config_current()
            for scope, (version, overrides) in current.items():
                self._layers[scope] = self._clean(scope, overrides)
                self._versions[scope] = version
            if not current:
                self._migrate(store)

    # ---- loading

    def _clean(self, scope, overrides):
        """Saved overrides without anything that is unknown or no longer valid (a bad value falls back, never stops the server)"""
        clean = {}
        for key, value in overrides.items():
            spec = spec_of(key)
            if spec is None or (spec.site_only and scope != SITE):
                continue
            try:
                clean[key] = _check(spec, value)
            except ValueError:
                pass
        return clean

    def _migrate(self, store):
        """The single settings table of the first version becomes version 1 of the site layer"""
        old = self._clean(SITE, store.saved_settings())
        if old:
            self._layers[SITE], self._versions[SITE] = old, 1
            store.config_add(SITE, 1, self._clock(), "migrated", "from the first settings table", old,
                             {key: [None, value] for key, value in old.items()})

    # ---- reading

    def default(self, key):
        """The factory value: config.py (when valid), else the built-in one"""
        spec = spec_of(key)
        if spec.config_name is None:
            return _engineering_specs()[1].get(key)
        try:
            return _check(spec, getattr(config, spec.config_name, spec.fallback))
        except ValueError:  # a typo in config.py must not take the page down
            return spec.fallback

    def _resolved(self, chip=None):
        out = {key: self.default(key) for key in keys()}
        out.update(self._layers[SITE])
        if chip is not None:
            out.update(self._layers.get(chip, {}))
        return out

    def resolved(self, chip=None):
        """Every key with the value in force for this mat (or for the site when no mat is given)"""
        with self._lock:
            return self._resolved(chip)

    def get(self, key, chip=None):
        return self.resolved(chip)[key]

    def values(self):
        return self.resolved()

    def source(self, key, chip=None):
        with self._lock:
            if chip is not None and key in self._layers.get(chip, {}):
                return "mat"
            return "site" if key in self._layers[SITE] else "factory"

    def describe(self, chip=None):
        """For the page: one entry per setting with its value in force, the value it falls back to, limits and source.
        With a mat: the settings that can be set per mat, `changed` meaning this mat overrides it."""
        with self._lock:
            scope = SITE if chip is None else chip
            value, above = self._resolved(chip), (self._resolved(None) if chip is not None else {key: self.default(key) for key in keys()})
            out = []
            for spec in all_specs():
                if chip is not None and spec.site_only:
                    continue
                out.append({"key": spec.key, "group": spec.group, "type": spec.type, "value": value[spec.key],
                            "default": above[spec.key], "min": spec.low, "max": spec.high, "unit": spec.unit,
                            "advanced": spec.advanced, "changed": spec.key in self._layers.get(scope, {}),
                            "source": ("mat" if chip is not None and spec.key in self._layers.get(chip, {}) else
                                       "site" if spec.key in self._layers[SITE] else "factory"),
                            **({"choices": list(spec.choices)} if spec.choices else {})})
            return out

    def layer(self, chip=None):
        """The overrides one layer holds (a copy): {key: value}"""
        with self._lock:
            return dict(self._layers.get(SITE if chip is None else chip, {}))

    def version(self, scope=SITE):
        return self._versions.get(scope, 0)

    def stamp(self, chip=None):
        """The settings version in force, e.g. "s3.m2" (site version 3, this mat's version 2); written on every alert"""
        with self._lock:
            return f"s{self._versions[SITE]}" + ("" if chip is None else f".m{self._versions.get(chip, 0)}")

    def scopes(self):
        """Mats that have their own layer"""
        with self._lock:
            return [scope for scope, layer in self._layers.items() if scope != SITE and layer]

    def history(self, scope=SITE, limit=50):
        """Newest first: [{scope, version, t, user, reason, changes}]"""
        if self._store is not None:
            return self._store.config_history(scope, limit)
        return [{"scope": scope, "version": v, "t": t, "user": user, "reason": reason, "changes": changes}
                for v, t, user, reason, _, changes in reversed(self._memory.get(scope, []))][:limit]

    # ---- changing

    def listen(self, listener, call=True):
        """listener(scope) is called after a change; scope is "site" or a mat's id (and, with `call`, once right away with "site")"""
        self._listeners.append(listener)
        if call:
            listener(SITE)

    def update(self, changes, scope=None, user=None, reason=""):
        """changes: {key: value, or None for "back to what the layer above says"} for the site layer, or for one mat.
        All or nothing: ValueError names the first bad one and nothing changes.
        Returns {key: (old, new)} (values in force) for what changed; {} when nothing did (no new version then)."""
        scope = SITE if scope in (None, SITE) else scope
        checked = {}
        for key, value in (changes or {}).items():
            spec = spec_of(key)
            if spec is None:
                raise ValueError(f"unknown setting {key}")
            if spec.site_only and scope != SITE:
                raise ValueError(f"{_label(key)} is a setting for the whole installation, not for one mat")
            checked[key] = None if value is None else _check(spec, value)
        with self._lock:
            new = dict(self._layers.get(scope, {}))
            for key, value in checked.items():
                if value is None:
                    new.pop(key, None)
                else:
                    new[key] = value
            changed = self._commit(scope, new, user, reason)
        self._notify(scope, changed)
        return changed

    def rollback(self, scope, version, user=None, reason=""):
        """Put the layer back as it was at `version` (a new version again). KeyError for a version that does not exist"""
        scope = SITE if scope in (None, SITE) else scope
        with self._lock:
            if self._store is not None:
                old = self._store.config_version(scope, version)
            else:
                old = {} if version == 0 else next((over for v, _, _, _, over, _ in self._memory.get(scope, []) if v == version), None)
            if old is None:
                raise KeyError(version)
            changed = self._commit(scope, self._clean(scope, old), user, reason or f"rolled back to version {version}")
        self._notify(scope, changed)
        return changed

    def _notify(self, scope, changed):
        if changed:   # outside the lock: a listener reads the settings again
            for listener in list(self._listeners):
                listener(scope)

    def _commit(self, scope, new, user, reason):
        """Validate the layer `new` in place of the current one and store it as the next version (the lock is held)"""
        old = self._layers.get(scope, {})
        touched = [key for key in {*old, *new} if old.get(key, MISSING) != new.get(key, MISSING)]
        if not touched:
            return {}
        before = self._resolved(None if scope == SITE else scope)
        self._layers[scope] = new
        try:
            self._validate_all(scope)
        except ValueError:
            self._layers[scope] = old
            raise
        after = self._resolved(None if scope == SITE else scope)
        changed = {key: (before[key], after[key]) for key in touched}
        version = self._versions.get(scope, 0) + 1
        self._versions[scope] = version
        now = self._clock()
        changes = {key: [before[key], after[key]] for key in touched}
        if self._store is not None:
            self._store.config_add(scope, version, now, user, reason or "", new, changes)
        else:
            self._memory.setdefault(scope, []).append((version, now, user, reason or "", dict(new), changes))
        return changed

    def _validate_all(self, scope):
        """The cross-checks on every full set the change can reach: the site set, and every mat's own set"""
        targets = [None, *self.scopes()] if scope == SITE else [scope]
        for chip in targets:
            try:
                _validate_resolved(self._resolved(chip))
            except ValueError as error:
                raise ValueError(f"{error}" + ("" if chip is None else f" (mat {chip})")) from error
