"""The desktop's SmartMat-server panel (gui/server_panel.py): the analysis-settings flows (compare, send, get, preview)
against a live server, without a display.

A small stand-in for tkinter is put in place only while the panel module is loaded (under its own module name), so this
runs where tkinter is missing and does not touch the real tkinter other tests use. It checks the panel's logic and
wiring (names, arguments, what is sent, what the status line says), not how Tk draws anything.
"""

import importlib.util
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from werkzeug.serving import make_server

from paths import resource_path
from processing.indices import default_indices
from processing.settings import default_settings
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine
from server.settings import Settings
from server.store import Store

ADMIN = "1234"
PANEL = Path(__file__).resolve().parent.parent / "gui" / "server_panel.py"
SAMPLE = str(resource_path("samples/seat_take1.json"))


# ---------------------------------------------------------------- a stand-in for tkinter

class Var:
    created = []

    def __init__(self, value=""):
        self.value = value
        Var.created.append(self)

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Widget:
    """Any widget: remembers its options, its children and (for a Toplevel) the callbacks waiting for the main loop"""
    registry = []
    queue = []          # (callable) waiting for "the main loop"; threads add to it, the test pumps it
    queue_lock = threading.Lock()

    def __init__(self, parent=None, **options):
        self.parent, self.options, self.children, self.alive = parent, options, [], True
        self.rows, self.state_flags, self.values = [], [], {}
        self.command = options.get("command")
        if isinstance(parent, Widget):
            parent.children.append(self)
        Widget.registry.append(self)

    def __getattr__(self, name):   # grid, pack, title, geometry, bind, protocol, focus_set, ... all do nothing
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None

    def after(self, ms, callback=None):
        with Widget.queue_lock:
            Widget.queue.append(callback)

    def winfo_exists(self):
        return self.alive

    def winfo_toplevel(self):
        return self

    def destroy(self):
        self.alive = False
        for child in self.children:
            child.alive = False

    def state(self, flags=None):
        if flags is not None:
            self.state_flags = list(flags)
        return self.state_flags

    def __setitem__(self, key, value):
        self.values[key] = value

    def __getitem__(self, key):
        return self.values[key]

    # Treeview
    def insert(self, parent, index, values=()):
        self.rows.append(tuple(values))
        return str(len(self.rows))

    def get_children(self):
        return [str(i + 1) for i in range(len(self.rows))]

    def delete(self, *items):
        self.rows.clear()


def fake_tk_modules():
    tk = types.ModuleType("tkinter")
    ttk = types.ModuleType("tkinter.ttk")
    messagebox = types.ModuleType("tkinter.messagebox")
    filedialog = types.ModuleType("tkinter.filedialog")
    tk.TclError = type("TclError", (Exception,), {})
    for name in ("LEFT", "RIGHT", "TOP", "BOTTOM", "BOTH", "X", "Y", "END", "W"):
        setattr(tk, name, name.lower())
    tk.StringVar, tk.BooleanVar = Var, Var
    tk.Toplevel = Widget
    for name in ("Frame", "Label", "Entry", "Button", "Treeview", "Checkbutton", "Radiobutton", "Progressbar", "LabelFrame"):
        setattr(ttk, name, type(name, (Widget,), {}))
    messagebox.askyesno = lambda *a, **k: messagebox.answer
    messagebox.answer = True
    filedialog.askopenfilename = lambda **k: filedialog.path
    filedialog.path = ""
    tk.ttk, tk.messagebox, tk.filedialog = ttk, messagebox, filedialog
    return {"tkinter": tk, "tkinter.ttk": ttk, "tkinter.messagebox": messagebox, "tkinter.filedialog": filedialog}


def load_panel_module():
    modules = fake_tk_modules()
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("server_panel_under_test", PANEL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, modules


def pump(until, seconds=60):
    """Run what the 'main loop' would: the callbacks queued by threads and by after(), until `until()` is true"""
    end = time.time() + seconds
    while time.time() < end:
        with Widget.queue_lock:
            batch, Widget.queue = Widget.queue, []
        for callback in batch:
            if callback is not None:
                callback()
        if until():
            return True
        time.sleep(0.01)
    return False


class FakeApp:
    def __init__(self, settings):
        self.settings, self.applied, self.mat = settings, [], "m1"

    def _profile_mat_id(self):
        return self.mat

    def current_settings(self):
        return self.settings

    def apply_engineering_settings(self, settings, name=None):
        self.applied.append((settings, name))

    def _save_profile(self):
        pass

    def _load_profile(self):
        return "restored"


def desktop_settings():
    settings = default_settings()
    settings["indices"] = default_indices()
    return settings


class PanelFlowTests(unittest.TestCase):
    def setUp(self):
        self.module, self.modules = load_panel_module()
        Widget.registry.clear()
        Widget.queue.clear()
        Var.created.clear()
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)
        self.store.add_user("Admin", "admin", ADMIN)
        self.settings = Settings(self.store)
        engines = {"m1": MatEngine("m1", 20, 20)}
        http = make_server("127.0.0.1", 0, create_app(self.store, AlertManager(stamp=self.settings.stamp), engines, settings=self.settings))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.shutdown)
        self.url = f"http://127.0.0.1:{http.server_port}"
        self.saved_url = self.url   # the address settings.json would hold: what was typed and saved last
        patch = mock.patch.object(self.module.app_settings, "save_server_url", lambda text: setattr(self, "saved_url", text))
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(self.module.app_settings, "effective_server_url", lambda: self.saved_url)
        patch.start()
        self.addCleanup(patch.stop)
        self.app = FakeApp(desktop_settings())
        self.panel = self.module.ServerPanel(Widget(), self.app)
        self.assertTrue(pump(lambda: not self.panel.busy and self.panel.shown_mat == "m1"))   # its first marker check is done
        self.panel.url_var.set(self.url)
        self.status = lambda: self.panel.status_var.get()
        self.messagebox, self.filedialog = self.modules["tkinter.messagebox"], self.modules["tkinter.filedialog"]

    def idle(self):
        return not self.panel.busy

    def run_flow(self, start, until=None):
        start()
        self.assertTrue(pump(until or self.idle), self.status())

    def windows(self, title_part=""):
        return [w for w in Widget.registry if w.alive and type(w).__name__ == "Widget"]

    def tables(self):
        return [w for w in Widget.registry if type(w).__name__ == "Treeview" and w.rows]

    def buttons(self, text):
        return [w for w in Widget.registry if type(w).__name__ == "Button" and w.options.get("text") == text and w.alive]

    # ---- compare

    def test_compare_says_how_many_differ_and_lists_them(self):
        self.app.settings["hotspots"]["activate_kpa"] = 33.0
        self.app.settings["contact_threshold_kpa"] = 2.5
        self.run_flow(self.panel._compare)
        self.assertEqual(self.status(), "2 analysis setting(s) differ from the server's.")
        rows = self.tables()[-1].rows
        self.assertEqual(sorted(row[0] for row in rows), ["contact threshold kpa", "hotspots: activate kpa"])
        self.assertIn(("hotspots: activate kpa", "33", "20", "factory"), rows)

    def test_compare_when_everything_matches(self):
        self.run_flow(self.panel._compare)
        self.assertEqual(self.status(), "Analysis settings match the server's.")
        self.assertEqual(self.tables(), [])            # nothing to list until "show the settings that match too"

    def test_a_server_that_cannot_be_reached_is_told_in_words(self):
        self.panel.url_var.set("http://127.0.0.1:1")
        self.run_flow(self.panel._compare)
        self.assertIn("Could not read the mat's settings from the server", self.status())
        self.assertIn("refused", self.status())

    def test_the_buttons_are_off_without_a_mat_and_while_busy(self):
        self.app.mat = None
        self.panel._set_states()
        self.assertTrue(all("disabled" in b.state_flags for b in self.panel.analysis_buttons))
        self.app.mat = "m1"
        self.panel.busy = True
        self.panel._set_states()
        self.assertTrue(all("disabled" in b.state_flags for b in self.panel.analysis_buttons))
        self.panel.busy = False
        self.panel._set_states()
        self.assertTrue(all("!disabled" in b.state_flags for b in self.panel.analysis_buttons))

    # ---- send

    def send_dialog(self, changes_ok=True):
        scope, reason, pin, error = Var.created[-4:]
        return scope, reason, pin, error

    def test_send_with_the_right_pin_saves_a_new_version_with_the_reason(self):
        self.app.settings["hotspots"]["activate_kpa"] = 33.0
        self.run_flow(self.panel._push, until=lambda: bool(self.buttons("Send")))
        scope, reason, pin, error = self.send_dialog()
        self.assertEqual(scope.get(), "mat")
        reason.set("soft cushion")
        pin.set(ADMIN)
        self.buttons("Send")[-1].command()
        self.assertTrue(pump(self.idle))
        self.assertEqual(self.status(), "Saved by Admin: settings version s0.m1")
        self.assertEqual(self.settings.get("hotspots.activate_kpa", "m1"), 33.0)
        self.assertEqual(self.settings.get("hotspots.activate_kpa", "m2"), 20.0)
        self.assertEqual(self.settings.history("m1")[0]["reason"], "soft cushion")
        self.assertEqual(pin.get(), "")                  # the PIN is not kept

    def test_send_for_the_whole_site(self):
        self.app.settings["movement"]["small_score"] = 0.2
        self.run_flow(self.panel._push, until=lambda: bool(self.buttons("Send")))
        scope, reason, pin, error = self.send_dialog()
        scope.set("site")
        pin.set(ADMIN)
        self.buttons("Send")[-1].command()
        self.assertTrue(pump(self.idle))
        self.assertEqual(self.settings.get("movement.small_score", "m2"), 0.2)
        self.assertEqual(self.settings.stamp("m2"), "s1.m0")

    def test_send_with_a_wrong_pin_or_none(self):
        self.app.settings["hotspots"]["activate_kpa"] = 33.0
        self.run_flow(self.panel._push, until=lambda: bool(self.buttons("Send")))
        scope, reason, pin, error = self.send_dialog()
        self.buttons("Send")[-1].command()               # no PIN typed: the dialog stays and says so
        self.assertEqual(error.get(), "Enter your PIN.")
        self.assertEqual(self.settings.version("m1"), 0)
        pin.set("0000")
        self.buttons("Send")[-1].command()
        self.assertTrue(pump(self.idle))
        self.assertEqual(self.status(), "Not saved: 403 Wrong PIN")
        self.assertEqual(self.settings.version("m1"), 0)

    def test_send_the_server_refuses_is_explained(self):
        self.app.settings["hotspots"]["deactivate_kpa"] = 99.0
        self.run_flow(self.panel._push, until=lambda: bool(self.buttons("Send")))
        self.send_dialog()[2].set(ADMIN)
        self.buttons("Send")[-1].command()
        self.assertTrue(pump(self.idle))
        self.assertTrue(self.status().startswith("Not saved: 400 Hotspot"), self.status())

    def test_nothing_to_send_when_they_match(self):
        self.run_flow(self.panel._push)
        self.assertIn("Nothing to send", self.status())
        self.assertEqual(self.buttons("Send"), [])

    # ---- get

    def test_get_applies_the_servers_values_after_asking(self):
        self.settings.update({"hotspots.activate_kpa": 28.0}, scope="m1", user="Admin")
        self.messagebox.answer = True
        self.run_flow(self.panel._pull)
        self.assertEqual(len(self.app.applied), 1)
        applied, name = self.app.applied[0]
        self.assertEqual((applied["hotspots"]["activate_kpa"], name), (28.0, "Server s0.m1"))
        self.assertIn("Applied the server's analysis settings", self.status())

    def test_get_asks_first_and_declining_changes_nothing(self):
        self.settings.update({"hotspots.activate_kpa": 28.0}, scope="m1", user="Admin")
        self.messagebox.answer = False
        self.run_flow(self.panel._pull)
        self.assertEqual((self.app.applied, self.status()), ([], "Nothing changed."))

    def test_get_when_they_match(self):
        self.run_flow(self.panel._pull)
        self.assertEqual(self.app.applied, [])
        self.assertIn("Nothing to get", self.status())

    def test_get_reports_a_desktop_that_refuses_the_values(self):
        self.settings.update({"hotspots.activate_kpa": 28.0}, scope="m1", user="Admin")
        self.app.apply_engineering_settings = mock.Mock(side_effect=ValueError("Hotspot thresholds are invalid"))
        self.run_flow(self.panel._pull)
        self.assertEqual(self.status(), "Could not apply them: Hotspot thresholds are invalid")

    # ---- preview

    def test_preview_replays_both_ways_and_shows_what_changes(self):
        eager = [
            {"name": "Load", "layer": "map", "threshold": 1.0, "near_fraction": 0.5,
             "terms": [{"signal": "exposure", "window_min": 15, "reference": 0.0001, "weight": 1.0, "inverted": False}]},
            {"name": "Overview", "layer": "summary", "threshold": 1.0, "near_fraction": 0.5,
             "terms": [{"source": "Load", "reducer": "peak", "region": "mat", "reference": 1.0, "weight": 1.0, "inverted": False}]}]
        self.app.settings["indices"] = eager
        self.settings.update({"alert_high_hold_s": 5}, scope="m1", user="Admin")   # the server's own alert delay for this mat
        self.filedialog.path = SAMPLE
        self.panel._preview()
        self.assertTrue(pump(lambda: self.status() == "Preview done.", 90), self.status())
        table = self.tables()[-1]
        self.assertTrue(any(row[0] == "With these settings" and row[1] == "high risk" for row in table.rows), table.rows)
        self.assertFalse(any(row[0] == "Now" for row in table.rows))               # the server as it is raises none
        labels = " ".join(w.options.get("text", "") for w in Widget.registry if type(w).__name__ == "Label")
        self.assertIn("Alerts the server would raise: 0 now, 1 with these settings", labels)
        self.assertIn("Settings tested: indices", labels)
        self.assertIn("seat_take1.json", labels)

    def test_preview_with_nothing_different_says_so_and_asks_for_no_file(self):
        self.filedialog.path = "should not be asked"
        self.run_flow(self.panel._preview)
        self.assertIn("Nothing differs from the server", self.status())

    def test_preview_cancelled_in_the_file_dialog(self):
        self.app.settings["hotspots"]["activate_kpa"] = 33.0
        self.filedialog.path = ""
        self.run_flow(self.panel._preview)
        self.assertEqual(self.status(), "Preview cancelled.")

    def test_preview_of_a_file_that_is_not_a_recording(self):
        self.app.settings["hotspots"]["activate_kpa"] = 33.0
        bad = self.dir / "bad.json"
        bad.write_text("{\"format\": \"nope\"}")
        self.filedialog.path = str(bad)
        self.run_flow(self.panel._preview)
        self.assertIn("Could not read the recording", self.status())

    def test_preview_can_be_cancelled_while_it_runs(self):
        self.app.settings["hotspots"]["activate_kpa"] = 33.0
        self.filedialog.path = SAMPLE
        self.panel._preview()
        self.assertTrue(pump(lambda: bool(self.buttons("Cancel")), 30))
        self.buttons("Cancel")[-1].command()
        pump(lambda: False, 0.5)
        self.assertEqual(self.status(), "Preview cancelled.")


if __name__ == "__main__":
    unittest.main()
