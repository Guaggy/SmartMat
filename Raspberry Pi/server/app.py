"""REST API and web UI of the SmartMat server. Viewing needs no login; every write carries the acting
user's PIN in its JSON body and is written to the event log with that user's name."""

import json
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import branding
import config
from processing import calibration
from processing.posture import risk_sort_key
from server.store import META_FIELDS

DEMO_PREFIX = getattr(config, "DEMO_PREFIX", "demo-")
SATURATION_WARN_CELLS = getattr(config, "SATURATION_WARN_CELLS", 1)
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_TIMELINE_HOURS = 24 * 7


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def create_app(store, alerts, engines, clock=time.time):
    """store: server.store.Store, alerts: AlertManager, engines: {chip_id: MatEngine} (the runner adds to it)"""
    app = Flask(__name__, static_folder=None)

    @app.errorhandler(ApiError)
    def api_error(error):
        return jsonify({"error": str(error)}), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"error": error.description}), error.code

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
                else ApiError(403, "wrong PIN")
        if admin and user["role"] != "admin":
            raise ApiError(403, "only an admin can do this")
        return user

    def known(chip_id):
        if chip_id not in engines and chip_id not in store.mats():
            raise ApiError(404, "unknown mat")

    def mat_info(chip_id, meta):
        row = meta.get(chip_id, {})
        return {"id": chip_id, "name": row.get("name") or chip_id, "room": row.get("room"), "seat": row.get("seat"),
                "unit": row.get("unit"), "demo": chip_id.startswith(DEMO_PREFIX)}

    def offline_snapshot():
        return {"online": False, "risk": "offline", "posture": "none", "time_in_position_s": None,
                "saturated_cells": 0, "since_relief_s": None, "occupied": None, "grid": None}

    # ---- reading

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/static/<path:name>")
    def static_file(name):
        return send_from_directory(STATIC_DIR, name)

    @app.route("/api/health")
    def health():
        return jsonify({"ok": True, "time": clock(), "mats": len(engines), "version": branding.VERSION})

    @app.route("/api/theme")
    def theme():
        return jsonify({name.lower(): getattr(branding, name, None)
                        for name in ("PALETTE_LIGHT", "PALETTE_DARK", "HEATMAP_STOPS")})

    @app.route("/api/overview")
    def overview():
        meta, open_alerts = store.mats(), alerts.open_alerts()
        rows = []
        for chip_id in set(engines) | set(meta):
            engine = engines.get(chip_id)
            snap = engine.snapshot() if engine is not None else offline_snapshot()
            rows.append(dict(mat_info(chip_id, meta), online=snap["online"], risk=snap["risk"],
                             posture=snap["posture"], time_in_position_s=snap["time_in_position_s"],
                             saturated_cells=snap["saturated_cells"],
                             saturated=snap["saturated_cells"] >= SATURATION_WARN_CELLS,
                             since_relief_s=snap["since_relief_s"],
                             open_alerts=sum(a["chip_id"] == chip_id and a["state"] == "open" for a in open_alerts)))
        rows.sort(key=lambda row: (*risk_sort_key(row), row["id"]))
        return jsonify({"time": clock(), "mats": rows,
                        "open_alerts": sum(a["state"] == "open" for a in open_alerts)})

    @app.route("/api/mats/<chip_id>")
    def one_mat(chip_id):
        known(chip_id)
        engine = engines.get(chip_id)
        now = clock()
        return jsonify(dict(mat_info(chip_id, store.mats()),
                            snapshot=engine.snapshot() if engine is not None else offline_snapshot(),
                            timeline=store.timeline(chip_id, now - 3600), alerts=alerts.open_alerts(chip_id)))

    @app.route("/api/mats/<chip_id>/timeline")
    def timeline(chip_id):
        known(chip_id)
        try:
            hours = min(max(float(request.args.get("hours", 1)), 0), MAX_TIMELINE_HOURS)
        except ValueError:
            raise ApiError(400, "hours must be a number")
        return jsonify({"id": chip_id, "timeline": store.timeline(chip_id, clock() - hours * 3600)})

    @app.route("/api/mats/<chip_id>/log")
    def mat_log(chip_id):
        known(chip_id)
        return jsonify({"id": chip_id, "events": store.events(chip_id)})

    @app.route("/api/alerts")
    def open_alerts():
        meta = store.mats()
        return jsonify({"alerts": [dict(a, name=mat_info(a["chip_id"], meta)["name"]) for a in alerts.open_alerts()]})

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
            raise ApiError(404, "no open alert with that id")
        store.log(clock(), "alert acknowledged" if action == "ack" else "alert ignored", alert["chip_id"],
                  user["name"], {"alert": alert_id, "kind": alert["kind"]})
        return jsonify(alert)

    @app.route("/api/mats/<chip_id>/meta", methods=["PUT"])
    def put_meta(chip_id):
        known(chip_id)
        data = body()
        user = actor(data)
        fields = {key: data[key] for key in META_FIELDS if key in data}
        if not fields:
            raise ApiError(400, f"send one of {', '.join(META_FIELDS)}")
        row = store.set_meta(chip_id, fields)
        store.log(clock(), "config changed", chip_id, user["name"], {"meta": fields})
        return jsonify(mat_info(chip_id, {chip_id: row}))

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
        new = dict(new, mat_id=chip_id, version=engine.profile_version + 1)
        try:
            engine.set_profile(new)
        except ValueError as error:
            raise ApiError(400, f"profile does not fit this mat: {error}")
        calibration.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        calibration.profile_path(chip_id).write_text(json.dumps(new, indent=2), encoding="utf-8")
        store.log(clock(), "calibration pushed", chip_id, user["name"], {"version": new["version"]})
        return jsonify({"ok": True, "user": user["name"], "id": chip_id, "version": new["version"]})

    @app.route("/api/users", methods=["GET", "POST"])
    def users():
        if request.method == "GET":
            return jsonify({"users": store.users(), "setup": store.user_count() == 0})
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
        return jsonify(user), 201

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
        return jsonify(user)

    return app
