"""The server's side of the mat passport (ESP32_China/PASSPORT.md): look at a mat's slots, take one as the mat's
calibration (adopt), and write the mat's current calibration back to its custom slot (backup / before shipping).

What goes in is device-bound data only: the calibration profile and, optionally, the mat's own analysis overrides. Names,
rooms, alert thresholds and users stay at the site. Every change is an audit-log event with who and why; adopting a slot
sets the mat's calibration through the same path as a pushed profile and its analysis overrides as a new version of the
mat's settings layer (so it can be rolled back like any other change).
"""

import json
import threading

from processing import calibration, passport
from passport_link import PassportError

ADOPT_ORDER = ("custom", "factory")   # a site's own calibration wins over the factory's


def apply_profile(engine, chip_id, profile, version=None):
    """Set a mat's calibration on its engine and save it: the one path for a pushed profile and an adopted passport.
    Returns the saved profile (with its new version). ValueError when it does not fit the mat; nothing changes then."""
    new = dict(profile, mat_id=chip_id, version=engine.profile_version + 1 if version is None else version)
    engine.set_profile(new)
    calibration.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    calibration.profile_path(chip_id).write_text(json.dumps(new, indent=2), encoding="utf-8")
    return new


def same_calibration(profile_a, profile_b):
    """Two profiles are the same calibration if they differ at most in bookkeeping (mat id, version, timestamps)"""
    def core(profile):
        return {k: v for k, v in (profile or {}).items() if k not in ("mat_id", "version", "created", "saved_at", "note")}
    return core(profile_a) == core(profile_b)


class PassportService:
    def __init__(self, link_factory, store, settings, engines, clock):
        """link_factory: () -> PassportLink (called when first needed, so a server without broker still starts)"""
        self._factory, self.store, self.settings, self.engines, self.clock = link_factory, store, settings, engines, clock
        self._link = None
        self._lock = threading.Lock()
        self.tried = set()    # mats whose zero-touch adoption was attempted this run

    @property
    def link(self):
        with self._lock:
            if self._link is None:
                self._link = self._factory()
            return self._link

    # ---- what is on the mat
    def status(self, chip_id):
        """{"serial", "slots": {slot: {bytes, crc, info | error, same_as_now}}}; PassportError when the mat does not answer"""
        summary = self.link.summary(chip_id)
        if summary is None:
            raise PassportError("the mat has not told the broker about its passport (older firmware, or offline)")
        engine = self.engines.get(chip_id)
        slots = {}
        for slot in passport.SLOTS:
            entry = summary.get(slot)
            if not entry:
                slots[slot] = None
                continue
            slots[slot] = dict(entry)
            try:
                document, _blob = self.link.read(chip_id, slot)
            except PassportError as error:
                slots[slot]["error"] = str(error)
                continue
            slots[slot].update(info=passport.describe(document), version=document["version"], by=document["written_by"],
                               at=document["written_at"], note=document["note"], has_analysis=bool(document.get("analysis")),
                               same_as_now=engine is not None and same_calibration(document["profile"], engine.profile))
        return {"serial": summary.get("serial", ""), "max": summary.get("max"), "slots": slots}

    # ---- taking a slot as the mat's calibration
    def adopt(self, chip_id, slot, user, reason=""):
        engine = self.engines.get(chip_id)
        if engine is None:
            raise PassportError("the mat is not connected to the server")
        document, _blob = self.link.read(chip_id, slot)
        profile = document["profile"]
        if list(engine.shape) not in (document["grid_shape"], document["grid_shape"][::-1]):
            raise PassportError("that passport is for a mat of another size")
        try:
            saved = apply_profile(engine, chip_id, profile)
        except ValueError as error:
            raise PassportError(f"the passport does not fit this mat: {error}") from error
        analysis = document.get("analysis")
        if analysis is not None:
            current = self.settings.layer(chip_id)
            changes = {key: None for key in current if key not in analysis}
            changes.update(analysis)
            try:
                self.settings.update(changes, scope=chip_id, user=user, reason=reason or f"passport {slot}")
            except ValueError as error:
                raise PassportError(f"the passport's analysis settings were refused: {error}") from error
        self.store.log(self.clock(), "passport adopted", chip_id, user,
                       {"slot": slot, "passport_version": document["version"], "profile_version": saved["version"],
                        "analysis": sorted(analysis) if analysis else []})
        return document

    def auto_adopt(self, chip_id):
        """A mat the server has no calibration for yet: take the passport it carries, custom before factory. Once per run.
        Returns the slot adopted, or None."""
        if chip_id in self.tried or calibration.load_profile(chip_id) is not None:
            return None
        self.tried.add(chip_id)
        try:
            summary = self.link.summary(chip_id)
            for slot in ADOPT_ORDER:
                if summary and summary.get(slot):
                    self.adopt(chip_id, slot, "system", "zero-touch: new mat brought its passport")
                    return slot
        except PassportError as error:
            self.store.log(self.clock(), "passport not adopted", chip_id, "system", {"why": str(error)})
        return None

    # ---- writing the mat's calibration to its custom slot
    def write(self, chip_id, user, note=""):
        engine = self.engines.get(chip_id)
        if engine is None:
            raise PassportError("the mat is not connected to the server")
        if engine.profile is None:
            raise PassportError("this mat has no calibration yet, so there is nothing to save")
        summary = self.link.summary(chip_id) or {}
        version = 1
        try:
            version = passport.decode(self.link.read(chip_id, "custom")[1])["version"] + 1
        except PassportError:
            pass
        analysis = self.settings.layer(chip_id) or None
        try:
            blob = passport.encode(passport.build("custom", summary.get("serial", ""), getattr(engine, "model", "") or "", engine.profile,
                                                  analysis, version, user, note, self.clock()))
        except ValueError as error:
            raise PassportError(str(error)) from error
        ack = self.link.write(chip_id, "custom", blob)
        self.store.log(self.clock(), "passport written", chip_id, user, {"slot": "custom", "version": version, "bytes": ack["bytes"]})
        return {"version": version, "bytes": ack["bytes"], "crc": ack["crc"]}
