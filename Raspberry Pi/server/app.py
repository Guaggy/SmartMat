"""REST API and web UI of the SmartMat server. Viewing needs no login; every write carries the acting
user's PIN in its JSON body and is written to the event log with that user's name. The JSON shapes are
documented in design/api-contract.md (that is what server/static/app.js reads)."""

import json
import subprocess
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import branding
import config
from matlink.passport_link import PassportError
from processing import calibration, passport
from processing.posture import risk_sort_key
from server import push
from server.passports import apply_profile
from server.settings import SITE, Settings
from server.store import DEVICE_FIELDS, META_FIELDS

DEMO_PREFIX = getattr(config, "DEMO_PREFIX", "demo-")
KIOSK_MARK = "smartmat-kiosk-profile"  # the --user-data-dir name deploy/smartmat-kiosk.sh gives the browser
STATIC_DIR = Path(__file__).resolve().parent / "static"
STARTED = int(time.time())
MAX_TIMELINE_HOURS = 24 * 7
SNAPSHOT_KEYS = ("unit", "scale_max", "grid", "occupied", "hotspots", "peak_kpa")


def cap(text):
    """Error texts are shown to nurses as they are: start with a capital"""
    return text[:1].upper() + text[1:]


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def create_app(store, alerts, engines, clock=time.time, settings=None, control=None, passports=None):
    """store: server.store.Store, alerts: AlertManager, engines: {chip_id: MatEngine} (the runner adds to it),
    settings: server.settings.Settings (the admin-editable values; defaults from config.py when not given),
    control: the runner, for removing and restoring mats (hide(chip_id, now), show(chip_id)); without it those are refused,
    passports: server.passports.PassportService (the mats' calibration kept on the mats); without it the passport routes answer 501"""
    settings = settings if settings is not None else Settings(store)
    app = Flask(__name__, static_folder=None)

    @app.errorhandler(ApiError)
    def api_error(error):
        return jsonify({"error": cap(str(error))}), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"error": cap(error.description)}), error.code

    @app.after_request
    def no_store(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ApiError(400, "send a JSON object")
        return data

    def actor(data, admin=False):
        """The user whose PIN is in the body, or an error (nothing is logged for a wrong PIN)"""
        if not data.get("pin"):
            raise ApiError(401, "PIN required")
        user, reason = store.check_pin(str(data["pin"]), clock(), key=request.remote_addr or "")
        if user is None:
            raise ApiError(429, "too many wrong PINs, try again later") if reason == "locked" \
                else ApiError(403, "Wrong PIN")
        if admin and user["role"] != "admin":
            raise ApiError(403, "only an admin can do this")
        return user

    def known(chip_id):
        if (chip_id not in engines and chip_id not in store.mats()) or chip_id in store.hidden_mats():
            raise ApiError(404, "unknown mat")

    def mat_info(chip_id, meta):
        row = meta.get(chip_id, {})
        return {"id": chip_id, "name": row.get("name") or chip_id, "room": row.get("room") or "",
                "seat": row.get("seat") or "", "unit": row.get("unit") or "", "demo": chip_id.startswith(DEMO_PREFIX)}

    def offline_snapshot():
        return {"online": False, "risk": "offline", "posture": "none", "time_in_position_s": None,
                "saturated_cells": 0, "since_relief_s": None}

    def mat_row(chip_id, meta, snap, open_alerts):
        """One overview row, also the head of the mat detail"""
        return dict(mat_info(chip_id, meta), online=snap["online"], risk=snap["risk"], posture=snap["posture"],
                    time_in_position_s=snap["time_in_position_s"], since_relief_s=snap["since_relief_s"],
                    saturated_cells=snap["saturated_cells"],
                    saturated=snap["saturated_cells"] >= settings.get("saturation_warn_cells"),
                    open_alerts=sum(a["chip_id"] == chip_id and a["state"] == "open" for a in open_alerts))

    # ---- reading

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/api/health")
    def health():
        # build changes when the server restarts or a static file changes: the kiosk page reloads itself on it
        build = f"{STARTED}-{int(max(f.stat().st_mtime for f in STATIC_DIR.iterdir() if f.is_file()))}"
        return jsonify({"ok": True, "time": clock(), "mats": len(engines), "version": branding.VERSION,
                        "needs_admin": store.user_count() == 0, "build": build})

    @app.route("/api/kiosk/exit", methods=["POST"])
    def kiosk_exit():
        """Closes the touchscreen kiosk browser (deploy/smartmat-kiosk.sh). Only the Pi itself may ask."""
        if request.remote_addr not in ("127.0.0.1", "::1"):
            return jsonify({"error": "Only from the touchscreen itself"}), 403
        subprocess.run(["pkill", "-f", KIOSK_MARK], check=False)
        return jsonify({"ok": True})

    @app.route("/api/theme")
    def theme():
        return jsonify({"light": branding.PALETTE_LIGHT, "dark": branding.PALETTE_DARK,
                        "heatmap_stops": [[t, list(rgb)] for t, rgb in branding.HEATMAP_STOPS]})

    @app.route("/api/overview")
    def overview():
        meta, open_alerts = store.mats(), alerts.open_alerts()
        rows = []
        for chip_id in (set(engines) | set(meta)) - store.hidden_mats():
            engine = engines.get(chip_id)
            rows.append(mat_row(chip_id, meta, engine.snapshot() if engine is not None else offline_snapshot(),
                                open_alerts))
        rows.sort(key=lambda row: (*risk_sort_key(row), row["id"]))
        return jsonify({"mats": rows, "open_alerts": sum(a["state"] == "open" for a in open_alerts),
                        "server_time": clock()})

    @app.route("/api/mats/<chip_id>")
    def one_mat(chip_id):
        known(chip_id)
        engine = engines.get(chip_id)
        snap = engine.snapshot() if engine is not None else offline_snapshot()
        has_frame = engine is not None and engine.last_t is not None
        detail = None
        if has_frame:  # an offline mat keeps its last picture; before the first frame there is none
            detail = {key: snap[key] for key in SNAPSHOT_KEYS}
            detail["indices"] = [i for i in snap["indices"] if i["state"] in ("ok", "near", "over")]
        age = round(max(0.0, engine.clock() - engine.last_t), 1) if has_frame else None
        return jsonify(dict(mat_row(chip_id, store.mats(), snap, alerts.open_alerts(chip_id)), snapshot=detail,
                            age_s=age, stale=not snap["online"]))

    @app.route("/api/mats/<chip_id>/timeline")
    def timeline(chip_id):
        known(chip_id)
        try:
            hours = min(max(float(request.args.get("hours", 1)), 0), MAX_TIMELINE_HOURS)
        except ValueError:
            raise ApiError(400, "hours must be a number")
        since = clock() - hours * 3600
        return jsonify({"segments": store.timeline(chip_id, since), "markers": store.handled(chip_id, since)})

    @app.route("/api/mats/<chip_id>/log")
    def mat_log(chip_id):
        known(chip_id)
        return jsonify({"id": chip_id, "events": store.events(chip_id)})

    @app.route("/api/alerts")
    def list_alerts():
        meta = store.mats()
        return jsonify({"alerts": [dict(a, name=mat_info(a["chip_id"], meta)["name"],
                                        room=mat_info(a["chip_id"], meta)["room"]) for a in alerts.recent()]})

    @app.route("/api/users", methods=["GET", "POST"])
    def users():
        if request.method == "GET":
            return jsonify({"users": store.users(), "needs_admin": store.user_count() == 0})
        data = body()
        first = store.user_count() == 0
        if first and data.get("role") != "admin":
            raise ApiError(400, "the first user must be an admin")
        by = None if first else actor(data, admin=True)["name"]
        try:
            user = store.add_user(data.get("name"), data.get("role"), data.get("new_pin"))
        except ValueError as error:
            raise ApiError(400, str(error))
        store.log(clock(), "user added", None, by or user["name"], {"name": user["name"], "role": user["role"]})
        return jsonify({"ok": True, "user": by or user["name"], "created": user}), 201

    def reason_of(data):
        reason = data.get("reason", "")
        if not isinstance(reason, str) or len(reason) > 200:
            raise ApiError(400, "the reason must be text of at most 200 characters")
        return reason.strip()

    def config_page(chip_id=None):
        """What the settings page of a scope shows: every setting with its value, where it comes from, and the version"""
        return {"scope": chip_id or SITE, "version": settings.version(chip_id or SITE), "stamp": settings.stamp(chip_id),
                "settings": settings.describe(chip_id)}

    def change_config(chip_id=None):
        """PUT of a scope: {pin, values: {key: value | null}, reason?}. All or nothing; a new version is kept"""
        data = body()
        user = actor(data, admin=True)
        values = data.get("values")
        if not isinstance(values, dict) or not values:
            raise ApiError(400, "send values: {setting: value, or null to inherit}")
        reason = reason_of(data)
        try:
            changed = settings.update(values, scope=chip_id, user=user["name"], reason=reason)
        except ValueError as error:
            raise ApiError(400, str(error))
        if changed:
            store.log(clock(), "config changed", chip_id, user["name"],
                      {"scope": chip_id or SITE, "version": settings.version(chip_id or SITE), "reason": reason,
                       "changes": {key: list(pair) for key, pair in changed.items()}})
        return jsonify(dict(config_page(chip_id), ok=True, user=user["name"]))

    @app.route("/api/settings", methods=["GET", "PUT"])
    def settings_route():
        """The site layer: what applies to every mat that does not override it"""
        if request.method == "GET":
            return jsonify(config_page())
        return change_config()

    @app.route("/api/mats/<chip_id>/config", methods=["GET", "PUT"])
    def mat_config(chip_id):
        """One mat's own layer on top of the site layer"""
        known(chip_id)
        if request.method == "GET":
            return jsonify(config_page(chip_id))
        return change_config(chip_id)

    @app.route("/api/config/history")
    def config_history():
        scope = request.args.get("scope", SITE)
        if scope != SITE:
            known(scope)
        try:
            limit = min(max(int(request.args.get("limit", 50)), 1), 500)
        except ValueError:
            raise ApiError(400, "limit must be a number")
        return jsonify({"scope": scope, "version": settings.version(scope), "history": settings.history(scope, limit)})

    @app.route("/api/config/rollback", methods=["POST"])
    def config_rollback():
        """Put a scope back as it was at an earlier version (that is a new version, the history stays)"""
        data = body()
        user = actor(data, admin=True)
        scope, version = data.get("scope", SITE), data.get("version")
        if scope != SITE:
            known(scope)
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ApiError(400, "version must be a whole number")
        reason = reason_of(data)
        try:
            changed = settings.rollback(scope, version, user=user["name"], reason=reason)
        except KeyError:
            raise ApiError(404, "no such version")
        except ValueError as error:
            raise ApiError(400, str(error))
        if changed:
            store.log(clock(), "config changed", None if scope == SITE else scope, user["name"],
                      {"scope": scope, "version": settings.version(scope), "reason": reason or f"rolled back to version {version}",
                       "changes": {key: list(pair) for key, pair in changed.items()}})
        return jsonify(dict(config_page(None if scope == SITE else scope), ok=True, user=user["name"], changed=len(changed)))

    # ---- writing (PIN in the body)

    @app.route("/api/alerts/<alert_id>/<action>", methods=["POST"])
    def handle_alert(alert_id, action):
        if action not in ("ack", "ignore"):
            raise ApiError(404, "unknown action")
        user = actor(body())
        try:
            handle = alerts.acknowledge if action == "ack" else alerts.ignore
            alert = handle(alert_id, user["name"], clock())
        except KeyError:
            raise ApiError(409, "This alert is no longer open")
        except ValueError as error:  # already handled by someone
            raise ApiError(409, str(error))
        store.log(clock(), "alert acknowledged" if action == "ack" else "alert ignored", alert["chip_id"],
                  user["name"], {"alert": alert_id, "kind": alert["kind"]})
        return jsonify({"ok": True, "user": user["name"], "alert": alert})

    @app.route("/api/mats/<chip_id>/meta", methods=["PUT"])
    def put_meta(chip_id):
        known(chip_id)
        data = body()
        user = actor(data, admin=True)   # names and rooms are what the alerts and the nurses' lists show
        fields = {key: data[key] for key in META_FIELDS if key in data}
        if not fields:
            raise ApiError(400, f"send one of {', '.join(META_FIELDS)}")
        if "name" in fields and not str(fields["name"]).strip():
            raise ApiError(400, "Name cannot be empty")
        row = store.set_meta(chip_id, fields)
        store.log(clock(), "config changed", chip_id, user["name"], {"meta": fields})
        return jsonify(dict(mat_info(chip_id, {chip_id: row}), ok=True, user=user["name"]))

    @app.route("/api/hidden-mats")
    def hidden_mats():
        meta = store.mats()
        return jsonify({"mats": [mat_info(chip_id, meta) for chip_id in sorted(store.hidden_mats())]})

    @app.route("/api/mats/<chip_id>/hide", methods=["POST"])
    def hide_mat(chip_id):
        known(chip_id)
        user = actor(body(), admin=True)
        if control is None:
            raise ApiError(501, "this server cannot remove mats")
        try:
            control.hide(chip_id, clock())
        except ValueError as error:
            raise ApiError(409, str(error))
        store.log(clock(), "mat removed", chip_id, user["name"])
        return jsonify({"ok": True, "user": user["name"]})

    @app.route("/api/mats/<chip_id>/show", methods=["POST"])
    def show_mat(chip_id):
        user = actor(body(), admin=True)
        if control is None:
            raise ApiError(501, "this server cannot restore mats")
        if chip_id not in store.hidden_mats() or not control.show(chip_id):
            raise ApiError(404, "that mat is not removed")
        store.log(clock(), "mat restored", chip_id, user["name"])
        return jsonify({"ok": True, "user": user["name"]})

    @app.route("/api/mats/<chip_id>/profile", methods=["GET", "PUT"])
    def profile(chip_id):
        engine = engines.get(chip_id)
        if engine is None:
            raise ApiError(404, "mat is not connected to the server")
        if request.method == "GET":
            return jsonify({"id": chip_id, "version": engine.profile_version, "profile": engine.profile})
        data = body()
        user = actor(data)
        new = data.get("profile")
        if not isinstance(new, dict) or new.get("format") != calibration.PROFILE_FORMAT:
            raise ApiError(400, f"profile must be a {calibration.PROFILE_FORMAT} object")
        try:
            new = apply_profile(engine, chip_id, new)
        except ValueError as error:
            raise ApiError(400, f"profile does not fit this mat: {error}")
        store.log(clock(), "calibration pushed", chip_id, user["name"], {"version": new["version"]})
        return jsonify({"ok": True, "user": user["name"], "id": chip_id, "version": new["version"]})

    # ---- the passport kept on the mat (calibration travels with the mat): look, adopt a slot, write the custom slot

    def passport_service():
        if passports is None:
            raise ApiError(501, "this server has no passport support")
        return passports

    @app.route("/api/mats/<chip_id>/passport")
    def passport_status(chip_id):
        known(chip_id)
        try:
            return jsonify(dict(passport_service().status(chip_id), id=chip_id))
        except PassportError as error:
            raise ApiError(502, str(error))

    @app.route("/api/mats/<chip_id>/passport/adopt", methods=["POST"])
    def passport_adopt(chip_id):
        data = body()
        user = actor(data, admin=True)
        known(chip_id)
        slot = data.get("slot")
        if slot not in ("factory", "custom"):
            raise ApiError(400, "slot must be factory or custom")
        try:
            document = passport_service().adopt(chip_id, slot, user["name"], reason_of(data))
        except PassportError as error:
            raise ApiError(502, str(error))
        return jsonify({"ok": True, "user": user["name"], "id": chip_id, "info": passport.describe(document)})

    @app.route("/api/mats/<chip_id>/passport/write", methods=["POST"])
    def passport_write(chip_id):
        data = body()
        user = actor(data, admin=True)
        known(chip_id)
        try:
            result = passport_service().write(chip_id, user["name"], str(data.get("note") or "")[:120])
        except PassportError as error:
            raise ApiError(502, str(error))
        return jsonify(dict(result, ok=True, user=user["name"], id=chip_id))

    # ---- phones for push notifications. Registering needs a valid PIN (anyone could otherwise subscribe to the alerts);
    # the push token is a secret of the phone, so changing or removing a registration needs no PIN.

    def device_fields(data):
        fields = {key: data[key] for key in DEVICE_FIELDS if key in data}
        if fields.get("lang") not in (None, *push.TEXTS):
            raise ApiError(400, f"lang must be one of {', '.join(push.TEXTS)}")
        if fields.get("tz") and not push.valid_zone(fields["tz"]):
            raise ApiError(400, "Unknown time zone")
        for key in ("quiet_from", "quiet_to"):
            if fields.get(key) and push.parse_hhmm(fields[key]) is None:
                raise ApiError(400, f"{key} must be HH:MM")
        if "name" in fields and fields["name"] is not None:
            fields["name"] = str(fields["name"]).strip()[:60]
        return fields

    @app.route("/api/devices", methods=["POST"])
    def add_device():
        data = body()
        user = actor(data)
        if data.get("platform") not in ("android", "ios"):
            raise ApiError(400, "platform must be android or ios")
        try:
            store.add_device(data.get("expo_push_token"), data["platform"], user["name"], clock(), **device_fields(data))
        except ValueError as error:
            raise ApiError(400, str(error))
        store.log(clock(), "device registered", None, user["name"], {"platform": data["platform"], "name": data.get("name")})
        return jsonify({"ok": True, "user": user["name"]}), 201

    @app.route("/api/devices/<token>", methods=["PUT", "DELETE"])
    def one_device(token):
        if request.method == "DELETE":
            if not store.remove_device(token):
                raise ApiError(404, "Unknown device")
            store.log(clock(), "device removed")
            return jsonify({"ok": True})
        try:
            store.update_device(token, **device_fields(body()))
        except KeyError:
            raise ApiError(404, "Unknown device")
        return jsonify({"ok": True})

    @app.route("/api/users/<int:user_id>", methods=["PUT"])
    def update_user(user_id):
        data = body()
        by = actor(data, admin=True)["name"]
        admins = [u["id"] for u in store.users() if u["role"] == "admin" and u["active"]]
        if data.get("active") is False and admins == [user_id]:
            raise ApiError(400, "keep at least one active admin")
        try:
            user = store.update_user(user_id, active=data.get("active"), pin=data.get("new_pin"))
        except KeyError:
            raise ApiError(404, "no such user")
        except ValueError as error:
            raise ApiError(400, str(error))
        changes = [name for name in ("active", "new_pin") if data.get(name) is not None]
        store.log(clock(), "user changed", None, by, {"name": user["name"], "changed": changes})
        return jsonify({"ok": True, "user": by, "updated": user})

    @app.route("/static/<path:name>")
    @app.route("/<path:name>")
    def static_file(name):
        """The page uses relative URLs (manifest.json, app.js, img/...), so the files are served from the root
        too. /api/* has its own routes; an unknown path ends in the JSON 404"""
        return send_from_directory(STATIC_DIR, name)

    return app
