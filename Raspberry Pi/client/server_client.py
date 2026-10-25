"""Desktop side of the SmartMat server's REST API (control plane): health, a mat's profile, its event log.

stdlib only. Every call returns (ok, data_or_error_text) and never raises: a refused connection, a timeout, a
4xx/5xx or a reply that is not JSON all become a readable text. The PIN of a write goes in the JSON body and is
never kept, logged or put in an error text.
"""

import hashlib
import http.client
import json
import urllib.error
import urllib.parse
import urllib.request

# not part of the calibration: the server's own counter and id, and any "..._at" timestamp (calibrated_at)
VOLATILE_KEYS = {"version", "mat_id"}


class ServerClient:
    def __init__(self, base_url, timeout=3):
        self.base_url = base_url.strip().rstrip("/")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # a LAN server, never via a proxy

    def health(self):
        """(True, {"ok", "version", "mats", ...}) or (False, text)"""
        return self._call("GET", "/api/health")

    def get_profile(self, chip):
        """(True, {"version": int, "profile": dict or None}); a mat the server does not know (404) has profile None"""
        ok, data = self._call("GET", f"/api/mats/{_quote(chip)}/profile")
        if not ok and data.startswith("404"):
            return True, {"id": chip, "version": 0, "profile": None}
        return ok, data

    def put_profile(self, chip, profile, pin):
        """(True, {"version": int, "user": name when the server says who}) or (False, text)"""
        return self._call("PUT", f"/api/mats/{_quote(chip)}/profile", {"profile": profile, "pin": pin})

    def get_config(self, chip=None):
        """(True, {"scope", "version", "stamp", "settings": [...]}) for one mat's settings (what is in force for it, and
        where each value comes from), or for the site layer when `chip` is None; (False, text) otherwise"""
        return self._call("GET", "/api/settings" if chip is None else f"/api/mats/{_quote(chip)}/config")

    def put_config(self, chip, values, pin, reason=""):
        """Set values of one mat's own layer (`chip`) or of the site layer (None). `values` is {key: value}, a null
        value meaning "inherit again". (True, the new page + {"user"}) or (False, text such as "403 Wrong PIN")"""
        path = "/api/settings" if chip is None else f"/api/mats/{_quote(chip)}/config"
        return self._call("PUT", path, {"values": values, "pin": pin, "reason": reason})

    def get_history(self, chip=None, limit=50):
        """(True, [version, ...] newest first: {version, t, user, reason, changes}) or (False, text)"""
        scope = "site" if chip is None else chip
        ok, data = self._call("GET", f"/api/config/history?scope={_quote(scope)}&limit={int(limit)}")
        if not ok:
            return ok, data
        history = data.get("history") if isinstance(data, dict) else None
        return (True, history) if isinstance(history, list) else (False, "the server sent no history")

    def get_overview(self):
        """(True, [mat, ...] as in /api/overview: id, name, online, risk, ...) or (False, text)"""
        ok, data = self._call("GET", "/api/overview")
        mats = data.get("mats") if ok and isinstance(data, dict) else None
        return (True, mats) if isinstance(mats, list) else (False, data if not ok else "the server sent no mat list")

    def get_snapshots(self, chip, since, until, limit=300, with_grids=True, after=False):
        """One page of a mat's snapshot history: (True, {"snapshots", "truncated", "next_from", "enabled", "interval_s"})
        or (False, text). Oldest first; `after` makes `since` exclusive (the next page starts at the last next_from)"""
        query = f"from={since:.3f}&to={until:.3f}&limit={int(limit)}"
        query += ("&with_grids=1" if with_grids else "") + ("&after=1" if after else "")
        return self._call("GET", f"/api/mats/{_quote(chip)}/history?{query}")

    def rollback(self, chip, version, pin, reason=""):
        """Put a layer back as it was at an earlier version (a new version again). (True, page) or (False, text)"""
        return self._call("POST", "/api/config/rollback", {"scope": "site" if chip is None else chip, "version": version,
                                                           "pin": pin, "reason": reason})

    def get_log(self, chip, limit=200):
        """(True, [event, ...] newest first) or (False, text)"""
        ok, data = self._call("GET", f"/api/mats/{_quote(chip)}/log?limit={int(limit)}")
        if not ok:
            return ok, data
        events = data.get("events") if isinstance(data, dict) else None
        return (True, events[:limit]) if isinstance(events, list) else (False, "the server sent no event list")

    def _call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        try:
            request = urllib.request.Request(self.base_url + path, data=data, method=method,
                                             headers={"Content-Type": "application/json"} if data else {})
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:  # before URLError, which it extends
            return False, _http_error_text(error)
        except urllib.error.URLError as error:
            return False, self._network_text(error.reason)
        except (OSError, http.client.HTTPException) as error:  # timeouts, resets, a half-sent reply
            return False, self._network_text(error)
        except ValueError:  # a URL urllib cannot use
            return False, f"not a usable server address: {self.base_url!r}"
        try:
            return True, json.loads(raw.decode("utf-8"))
        except ValueError:
            return False, f"{self.base_url} answered, but not with JSON (is this a SmartMat server?)"

    def _network_text(self, reason):
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            return f"no answer from {self.base_url} within {self.timeout:g} s"
        if isinstance(reason, ConnectionRefusedError):
            return f"{self.base_url} refused the connection (is the server running, and the port right?)"
        return f"cannot reach {self.base_url}: {reason}"


def _quote(chip):
    return urllib.parse.quote(str(chip), safe="")


def _http_error_text(error):
    """The server's own {"error": text} when it sent one (written for a nurse), else the status line"""
    try:
        text = json.loads(error.read().decode("utf-8")).get("error")
    except (OSError, ValueError, AttributeError):
        text = None
    return f"{error.code} {text or error.reason}"


# ---- is this mat's calibration the one on the server?

def _calibration_content(value):
    if isinstance(value, dict):
        return {key: _calibration_content(item) for key, item in value.items()
                if key not in VOLATILE_KEYS and not key.endswith("_at")}
    if isinstance(value, list):
        return [_calibration_content(item) for item in value]
    return value


def profile_fingerprint(profile):
    """sha256 of the canonical JSON of the calibration content of a mat profile (tare, both calibrations,
    orientation, size, ROI); the server's version and mat_id and every timestamp are left out"""
    text = json.dumps(_calibration_content(profile), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_profiles(local, remote):
    """"matches", "differs" or "not_on_server" (remote None/empty = the server has nothing for this mat)"""
    if not remote:
        return "not_on_server"
    if not local:
        return "differs"
    return "matches" if profile_fingerprint(local) == profile_fingerprint(remote) else "differs"
