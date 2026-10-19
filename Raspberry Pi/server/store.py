"""The server's sqlite database (smartmat.db in the data dir): users, mat metadata, an append-only event log
and the posture/risk timeline. No patient names anywhere: mats are named by room and seat."""

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading

import config

RETENTION_DAYS = getattr(config, "RETENTION_DAYS", 30)
LOCKOUT_ATTEMPTS = getattr(config, "PIN_LOCKOUT_ATTEMPTS", 0)
LOCKOUT_S = getattr(config, "PIN_LOCKOUT_S", 60)
ROLES = ("admin", "user")
META_FIELDS = ("name", "room", "seat", "unit")
DEVICE_FIELDS = ("name", "lang", "tz", "quiet_from", "quiet_to")  # a phone may change these without a PIN
PUSH_TOKEN = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{1,200}\]$")
SEGMENT_GAP_S = 5.0  # a timeline segment is not stretched over a longer gap (server down)
# ponytail: light scrypt so a PIN-only check can try every user quickly; a 4-6 digit PIN cannot resist an
# offline guess anyway, the hash only keeps PINs from being read off the file
SCRYPT = {"n": 2 ** 10, "r": 8, "p": 1, "dklen": 32}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, role TEXT NOT NULL,
    pin_hash TEXT NOT NULL, salt TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS mats (chip_id TEXT PRIMARY KEY, name TEXT, room TEXT, seat TEXT, unit TEXT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL NOT NULL, chip_id TEXT,
    kind TEXT NOT NULL, user TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS timeline (id INTEGER PRIMARY KEY, chip_id TEXT NOT NULL, t_start REAL NOT NULL,
    t_end REAL NOT NULL, posture TEXT, risk TEXT);
CREATE TABLE IF NOT EXISTS devices (token TEXT PRIMARY KEY, platform TEXT, name TEXT, lang TEXT NOT NULL DEFAULT 'nb',
    tz TEXT, quiet_from TEXT, quiet_to TEXT, user TEXT, t_registered REAL NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, chip_id TEXT NOT NULL, kind TEXT NOT NULL, t_raised REAL NOT NULL,
    since REAL, t_cleared REAL, state TEXT NOT NULL, by TEXT, t_handled REAL);
CREATE INDEX IF NOT EXISTS timeline_mat ON timeline (chip_id, t_end);
CREATE INDEX IF NOT EXISTS events_mat ON events (chip_id, id);
"""


def _hash(pin, salt):
    return hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), **SCRYPT).hex()


def valid_pin(pin):
    return isinstance(pin, str) and pin.isdigit() and 4 <= len(pin) <= 8


class Store:
    def __init__(self, path, lockout_attempts=LOCKOUT_ATTEMPTS, lockout_s=LOCKOUT_S):
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        try:  # the timeline is written every second: WAL keeps that off the SD card's fsync path and survives a power cut
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:  # a file system that cannot do it keeps the default journal
            pass
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()  # one connection shared by the web requests and the tick
        self.lockout_attempts, self.lockout_s = lockout_attempts, lockout_s
        self._failures = {}   # client key -> (wrong PINs in a row, locked until)
        self._segments = {}   # chip_id -> (row id, posture, risk, t_end) of the open timeline segment

    def close(self):
        with self._lock:
            self._db.close()

    def _rows(self, sql, args=()):
        with self._lock:
            return [dict(row) for row in self._db.execute(sql, args)]

    # ---- users and PINs

    def user_count(self):
        return self._rows("SELECT COUNT(*) AS n FROM users")[0]["n"]

    def users(self):
        """id, name, role, active (never the PIN hash)"""
        return [dict(row, active=bool(row["active"]))
                for row in self._rows("SELECT id, name, role, active FROM users ORDER BY id")]

    def _pin_owner(self, pin):
        for user in self._rows("SELECT * FROM users WHERE active = 1"):
            if hmac.compare_digest(_hash(pin, user["salt"]), user["pin_hash"]):
                return {key: user[key] for key in ("id", "name", "role", "active")}
        return None

    def add_user(self, name, role, pin):
        """New user; ValueError for a bad name/role/PIN, a taken name or a PIN another user has"""
        name = str(name or "").strip()
        if not name or len(name) > 40:
            raise ValueError("name must be 1-40 characters")
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")
        self._check_new_pin(pin)
        salt = os.urandom(16).hex()
        try:
            with self._lock, self._db:
                cursor = self._db.execute("INSERT INTO users (name, role, pin_hash, salt) VALUES (?, ?, ?, ?)",
                                          (name, role, _hash(pin, salt), salt))
        except sqlite3.IntegrityError as error:
            raise ValueError("a user with that name exists") from error
        return {"id": cursor.lastrowid, "name": name, "role": role, "active": True}

    def update_user(self, user_id, active=None, pin=None):
        """Disable/enable a user or reset their PIN; KeyError if there is no such user"""
        if not self._rows("SELECT id FROM users WHERE id = ?", (user_id,)):
            raise KeyError(user_id)
        if pin is not None:
            self._check_new_pin(pin, user_id)
            salt = os.urandom(16).hex()
            with self._lock, self._db:
                self._db.execute("UPDATE users SET pin_hash = ?, salt = ? WHERE id = ?",
                                 (_hash(pin, salt), salt, user_id))
        if active is not None:
            with self._lock, self._db:
                self._db.execute("UPDATE users SET active = ? WHERE id = ?", (int(bool(active)), user_id))
        return next(user for user in self.users() if user["id"] == user_id)

    def _check_new_pin(self, pin, user_id=None):
        if not valid_pin(pin):
            raise ValueError("PIN must be 4-8 digits")
        owner = self._pin_owner(pin)
        if owner is not None and owner["id"] != user_id:
            raise ValueError("That PIN is already in use, choose another")  # the PIN alone says who is acting, so it must be unique

    def check_pin(self, pin, t, key=""):
        """(user, None) for a right PIN, else (None, reason); reason 'locked' while `key` (the client) is
        locked out after PIN_LOCKOUT_ATTEMPTS wrong PINs in a row (0 = never)"""
        count, until = self._failures.get(key, (0, 0))
        if self.lockout_attempts and t < until:
            return None, "locked"
        user = self._pin_owner(pin) if valid_pin(pin) else None
        if user is not None:
            self._failures.pop(key, None)
            return user, None
        count += 1
        locked = self.lockout_attempts and count >= self.lockout_attempts
        self._failures[key] = (0, t + self.lockout_s) if locked else (count, 0)
        return None, "wrong"

    # ---- mats

    def mats(self):
        return {row["chip_id"]: row for row in self._rows("SELECT * FROM mats")}

    def set_meta(self, chip_id, fields):
        """Update some of name/room/seat/unit (missing ones are kept)"""
        current = self.mats().get(chip_id, {})
        values = [str(fields[key]).strip()[:60] if fields.get(key) is not None else current.get(key)
                  for key in META_FIELDS]
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO mats (chip_id, name, room, seat, unit) VALUES (?, ?, ?, ?, ?)",
                             (chip_id, *values))
        return self.mats()[chip_id]

    # ---- phones that get push notifications (Expo push tokens)

    def devices(self):
        return self._rows("SELECT * FROM devices ORDER BY t_registered")

    def add_device(self, token, platform, user, t, **fields):
        """Register (or re-register) a phone. ValueError for something that is not an Expo push token"""
        if not isinstance(token, str) or not PUSH_TOKEN.match(token):
            raise ValueError("That is not an Expo push token")
        values = {key: fields.get(key) for key in DEVICE_FIELDS}
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO devices (token, platform, name, lang, tz, quiet_from, quiet_to, user,"
                             " t_registered) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (token, platform, values["name"], values["lang"] or "nb", values["tz"], values["quiet_from"],
                              values["quiet_to"], user, t))

    def update_device(self, token, **fields):
        """Change name/lang/tz/quiet window of a registered phone; KeyError if the token is unknown"""
        if token not in {row["token"] for row in self.devices()}:
            raise KeyError(token)
        fields = {key: fields[key] for key in DEVICE_FIELDS if key in fields}
        if fields:
            with self._lock, self._db:
                self._db.execute(f"UPDATE devices SET {', '.join(f'{key} = ?' for key in fields)} WHERE token = ?",
                                 (*fields.values(), token))

    def remove_device(self, token):
        with self._lock, self._db:
            return self._db.execute("DELETE FROM devices WHERE token = ?", (token,)).rowcount > 0

    # ---- alerts (saved so a restart neither forgets them nor raises and pushes them again)

    ALERT_FIELDS = ("id", "chip_id", "kind", "t_raised", "since", "t_cleared", "state", "by", "t_handled")

    def save_alert(self, alert):
        with self._lock, self._db:
            self._db.execute(f"INSERT OR REPLACE INTO alerts ({', '.join(self.ALERT_FIELDS)}) "
                             f"VALUES ({', '.join('?' * len(self.ALERT_FIELDS))})",
                             tuple(alert.get(key) for key in self.ALERT_FIELDS))

    def saved_alerts(self, history=30):
        """Every uncleared alert plus the `history` most recent handled ones that have cleared"""
        return (self._rows("SELECT * FROM alerts WHERE t_cleared IS NULL")
                + self._rows("SELECT * FROM alerts WHERE t_cleared IS NOT NULL AND state != 'open' "
                             "ORDER BY t_cleared DESC LIMIT ?", (int(history),)))

    # ---- event log (append-only) and timeline

    def log(self, t, kind, chip_id=None, user=None, detail=None):
        with self._lock, self._db:
            self._db.execute("INSERT INTO events (t, chip_id, kind, user, detail) VALUES (?, ?, ?, ?, ?)",
                             (t, chip_id, kind, user, None if detail is None else json.dumps(detail)))

    def events(self, chip_id=None, limit=200):
        """Newest first"""
        where, args = ("WHERE chip_id = ?", (chip_id,)) if chip_id is not None else ("", ())
        rows = self._rows(f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?", (*args, int(limit)))
        for row in rows:
            row["detail"] = None if row["detail"] is None else json.loads(row["detail"])
        return rows

    def handled(self, chip_id, since):
        """Alerts acknowledged or ignored since `since`, for the timeline markers: [{t, kind, user}]"""
        return self._rows("SELECT t, 'handled' AS kind, user FROM events WHERE chip_id = ? AND t >= ? "
                          "AND kind IN ('alert acknowledged', 'alert ignored') ORDER BY t", (chip_id, since))

    def record_states(self, t, states):
        """One tick: [(chip_id, posture, risk)]; extends each mat's open segment or starts a new one"""
        with self._lock, self._db:
            for chip_id, posture, risk in states:
                segment = self._segments.get(chip_id)
                if segment and segment[1:3] == (posture, risk) and t - segment[3] <= SEGMENT_GAP_S:
                    self._db.execute("UPDATE timeline SET t_end = ? WHERE id = ?", (t, segment[0]))
                    row_id = segment[0]
                else:
                    if segment and t - segment[3] <= SEGMENT_GAP_S:  # close the old one where the new one starts
                        self._db.execute("UPDATE timeline SET t_end = ? WHERE id = ?", (t, segment[0]))
                    row_id = self._db.execute(
                        "INSERT INTO timeline (chip_id, t_start, t_end, posture, risk) VALUES (?, ?, ?, ?, ?)",
                        (chip_id, t, t, posture, risk)).lastrowid
                self._segments[chip_id] = (row_id, posture, risk, t)

    def timeline(self, chip_id, since):
        return self._rows("SELECT t_start, t_end, posture, risk FROM timeline WHERE chip_id = ? AND t_end >= ? "
                          "ORDER BY t_start", (chip_id, since))

    def purge(self, t, days=RETENTION_DAYS):
        """Delete events and timeline older than the retention period"""
        cutoff = t - days * 86400
        with self._lock, self._db:
            self._db.execute("DELETE FROM events WHERE t < ?", (cutoff,))
            self._db.execute("DELETE FROM timeline WHERE t_end < ?", (cutoff,))
            self._db.execute("DELETE FROM alerts WHERE t_cleared IS NOT NULL AND t_cleared < ?", (cutoff,))
