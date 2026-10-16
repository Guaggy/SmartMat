"""Desktop SmartMat-server client: against a stub HTTP server and the real Flask app, fingerprints, the Tk group."""

import copy
import json
import shutil
import tempfile
import threading
import time
import tkinter as tk
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from processing import calibration
from processing.calibration import Calibration, PressureCalibration
from server_client import ServerClient, compare_profiles, profile_fingerprint
from server.engine import grid_shape
from test_server_engine import profile  # pytest puts tests/ on sys.path


class Stub(BaseHTTPRequestHandler):
    """GET /ok, /slow, /html and /api/health answer; anything else is a 403 with an {"error"} body"""

    seen = []

    def log_message(self, *args):
        pass

    def reply(self, status, body, kind="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            self.reply(200, b'{"ok": true, "version": "9.9", "mats": 2}')
        elif self.path.startswith("/api/mats/m1/log"):
            self.reply(200, json.dumps({"id": "m1", "events": [{"id": i} for i in range(5)]}).encode())
        elif self.path == "/api/mats/gone/profile":
            self.reply(404, b'{"error": "mat is not connected to the server"}')
        elif self.path == "/api/mats/slow/profile":
            time.sleep(1.0)
            self.reply(200, b"{}")
        elif self.path == "/api/mats/html/profile":
            self.reply(200, b"<html>router login</html>", "text/html")
        else:
            self.reply(500, b"boom")

    def do_PUT(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append(body)
        if body.get("pin") == "1234":
            self.reply(200, b'{"ok": true, "user": "Kari", "version": 3}')
        else:
            self.reply(403, b'{"error": "wrong PIN"}')


def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = serve(Stub)
        cls.client = ServerClient(cls.url, timeout=0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_and_log_success(self):
        self.assertEqual(self.client.health(), (True, {"ok": True, "version": "9.9", "mats": 2}))
        ok, events = self.client.get_log("m1", limit=3)
        self.assertTrue(ok)
        self.assertEqual([e["id"] for e in events], [0, 1, 2])

    def test_put_sends_pin_in_the_body_and_reads_user_or_server_error(self):
        self.assertEqual(self.client.put_profile("m1", {"a": 1}, "1234"), (True, {"ok": True, "user": "Kari", "version": 3}))
        self.assertEqual(Stub.seen[-1], {"profile": {"a": 1}, "pin": "1234"})
        self.assertEqual(self.client.put_profile("m1", {"a": 1}, "0000"), (False, "403 Wrong PIN"))

    def test_http_errors_become_text(self):
        ok, text = self.client.get_profile("other")
        self.assertFalse(ok)
        self.assertTrue(text.startswith("500"), text)

    def test_unknown_mat_is_a_missing_profile_not_an_error(self):
        self.assertEqual(self.client.get_profile("gone"), (True, {"id": "gone", "version": 0, "profile": None}))

    def test_slow_server_times_out(self):
        ok, text = self.client.get_profile("slow")
        self.assertFalse(ok)
        self.assertIn("no answer", text)

    def test_not_json_is_readable(self):
        ok, text = self.client.get_profile("html")
        self.assertFalse(ok)
        self.assertIn("not with JSON", text)

    def test_refused_and_nonsense_urls_never_raise(self):
        server, url = serve(Stub)
        server.shutdown()
        server.server_close()  # the port is now closed
        for client in (ServerClient(url, 0.3), ServerClient("not a url"), ServerClient("ftp://x"), ServerClient("")):
            for ok, text in (client.health(), client.get_profile("m1"), client.put_profile("m1", {}, "1"),
                             client.get_log("m1")):
                self.assertFalse(ok)
                self.assertIsInstance(text, str)
                self.assertTrue(text)
        text = ServerClient(url, 3).health()[1]  # Windows retries a closed port for ~2 s before refusing
        self.assertTrue("refused" in text or "no answer" in text, text)


class FingerprintTests(unittest.TestCase):
    def test_ignores_version_mat_id_and_timestamps(self):
        local = profile()
        remote = copy.deepcopy(local)
        remote.update(version=7, mat_id="chip")
        remote["individual"]["calibrated_at"] = "2030-01-01"
        remote["uniform"]["calibrated_at"] = None
        self.assertEqual(profile_fingerprint(local), profile_fingerprint(remote))
        self.assertEqual(compare_profiles(local, remote), "matches")

    def test_detects_calibration_changes(self):
        local = profile()
        for change in (lambda p: p["orientation"].update(mirror_h=True),
                       lambda p: p.update(baseline=[[1.0]]),
                       lambda p: p["uniform"].update(offset=p["uniform"]["offset"] + 1),
                       lambda p: p.update(active="uniform"),
                       lambda p: p["individual"]["cells"][0].update(offset=99)):
            other = copy.deepcopy(local)
            change(other)
            self.assertEqual(compare_profiles(local, other), "differs")

    def test_not_on_server(self):
        self.assertEqual(compare_profiles(profile(), None), "not_on_server")
        self.assertEqual(compare_profiles(profile(), {}), "not_on_server")

    def test_a_profile_survives_save_apply_save(self):
        """After Get from server the live state is saved again: it must still match what the server holds"""
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        with mock.patch.object(calibration, "PROFILES_DIR", folder), grid_shape(20, 20):
            first = Calibration()
            first.baseline = np.full((20, 20), 3.5)
            pressure = PressureCalibration.default()
            calibration.save_profile("a", first.baseline, pressure, {"rotation": 0, "mirror_h": True, "mirror_v": False},
                                     (500.0, 400.0))
            saved = calibration.load_profile("a")
            second, pressure2 = Calibration(), PressureCalibration()
            calibration.apply_profile(saved, second, pressure2)
            calibration.save_profile("b", second.baseline, pressure2, saved["orientation"], (500.0, 400.0))
            again = calibration.load_profile("b")
        self.assertEqual(compare_profiles(saved, again), "matches")


class RealServerTests(unittest.TestCase):
    """The client against the real Flask app over real HTTP"""

    def setUp(self):
        try:
            from werkzeug.serving import make_server
            from server.alerts import AlertManager
            from server.app import create_app
            from server.engine import MatEngine
            from server.store import Store
        except ImportError as error:
            self.skipTest(f"server dependencies missing: {error}")
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        self.enterContext(mock.patch.object(calibration, "PROFILES_DIR", folder / "profiles"))
        store = Store(folder / "smartmat.db", lockout_attempts=0, lockout_s=60)
        self.addCleanup(store.close)
        store.add_user("Kari", "admin", "1234")
        app = create_app(store, AlertManager(high_hold_s=0, offline_hold_s=0), {"m1": MatEngine("m1", 20, 20)})
        server = make_server("127.0.0.1", 0, app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.client = ServerClient(f"http://127.0.0.1:{server.server_port}")

    def test_put_then_get_bumps_the_version(self):
        ok, data = self.client.health()
        self.assertTrue(ok and data["ok"])
        self.assertEqual(self.client.get_profile("m1"), (True, {"id": "m1", "version": 0, "profile": None}))
        self.assertEqual(self.client.get_profile("nope"), (True, {"id": "nope", "version": 0, "profile": None}))
        ok, data = self.client.put_profile("m1", profile(), "1234")
        self.assertTrue(ok, data)
        self.assertEqual((data["version"], data["user"]), (1, "Kari"))
        ok, data = self.client.put_profile("m1", profile(mirror_h=True), "1234")
        self.assertEqual(data["version"], 2)
        ok, data = self.client.get_profile("m1")
        self.assertEqual(data["version"], 2)
        self.assertEqual(compare_profiles(profile(mirror_h=True), data["profile"]), "matches")
        self.assertEqual(compare_profiles(profile(), data["profile"]), "differs")
        self.assertEqual(self.client.put_profile("m1", profile(), "9999"), (False, "403 Wrong PIN"))
        ok, events = self.client.get_log("m1")
        self.assertTrue(ok)
        self.assertEqual([e["kind"] for e in events], ["calibration pushed"] * 2)


class PanelTests(unittest.TestCase):
    def test_group_builds_and_disables_mat_buttons_without_a_mat(self):
        from gui.server_panel import ServerPanel
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(root.destroy)
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        import app_settings
        self.enterContext(mock.patch.object(app_settings, "FILE", folder / "settings.json"))
        app = SimpleNamespace(_profile_mat_id=lambda: None)
        panel = ServerPanel(root, app)
        panel.frame.pack()
        root.update()
        self.assertEqual(str(panel.mat_buttons[0].cget("text")), "Send calibration to server")
        self.assertTrue(all(button.instate(["disabled"]) for button in panel.mat_buttons))
        self.assertFalse(panel.test_button.instate(["disabled"]))
        self.assertIn("Connect a real mat", panel.hint_var.get())
        self.assertEqual(panel.marker_var.get(), "Calibration: server not set")
        app._profile_mat_id = lambda: "chip1"
        root.update()
        panel._tick()
        self.assertFalse(any(button.instate(["disabled"]) for button in panel.mat_buttons))
        self.assertEqual(panel.hint_var.get(), "")


if __name__ == "__main__":
    unittest.main()
