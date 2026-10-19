"""The desktop's passport panel (gui/passport_panel.py) without a display: a stand-in for tkinter (the one of
test_server_panel_logic) and the Python stand-in for the mat's firmware on an in-process bus. Checks the wiring: what the
buttons do, what the status line says, what is written to the mat."""

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from passport_fake import FakePassportDevice
from passport_link import LoopbackBus, PassportLink
from processing import calibration, passport
from server.__main__ import demo_profile

from test_server_panel_logic import FakeApp, Widget, Var, fake_tk_modules, pump

PANEL = Path(__file__).resolve().parent.parent / "gui" / "passport_panel.py"


def load_module():
    modules = fake_tk_modules()
    with mock.patch.dict(sys.modules, modules):
        for name in [n for n in sys.modules if n == "gui.server_panel" or n == "gui.passport_panel"]:
            del sys.modules[name]
        spec = importlib.util.spec_from_file_location("passport_panel_under_test", PANEL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, modules


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.module, self.modules = load_module()
        Widget.registry.clear()
        Widget.queue.clear()
        Var.created.clear()
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        for patch in (mock.patch.object(calibration, "PROFILES_DIR", self.dir),
                      mock.patch.object(self.module.config, "TOTAL_ROWS", 20), mock.patch.object(self.module.config, "TOTAL_COLS", 20)):
            patch.start()
            self.addCleanup(patch.stop)
        bus = LoopbackBus()
        self.device = FakePassportDevice(bus.transport(), "m1", "SM-5", "key")
        self.link = PassportLink(bus.transport(), 0.3)
        patch = mock.patch.object(self.module.passport_sync, "connect", lambda *a, **k: (True, self.link))
        patch.start()
        self.addCleanup(patch.stop)
        self.link.close = lambda: None      # the bus outlives each button press
        self.app = FakeApp({})
        self.app.applied_profiles = []
        self.panel = self.module.PassportPanel(Widget(), self.app)
        self.messagebox = self.modules["tkinter.messagebox"]

    def press(self, command):
        command()
        self.assertTrue(pump(lambda: not self.panel.busy), self.panel.status_var.get())

    def test_show_lists_serial_and_slots(self):
        self.press(self.panel._show)
        self.assertEqual(self.panel.lines_var.get(), "Serial number: SM-5\nFactory: empty\nCustom: empty")

    def test_buttons_are_off_without_a_mat(self):
        self.app.mat = None
        self.panel._set_states()
        self.assertTrue(all("disabled" in b.state_flags for b in self.panel.buttons))
        self.assertEqual(self.panel.status_var.get(), self.module.NO_MAT_HINT)

    def test_save_writes_the_custom_slot_with_the_note_and_rising_version(self):
        calibration.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        calibration.profile_path("m1").write_text(__import__("json").dumps(demo_profile(20, 20)), encoding="utf-8")
        self.panel.note_var.set("for the school")
        self.press(self.panel._save)
        self.assertEqual(self.panel.status_var.get(), "Saved to the mat (custom, version 1).")
        document = passport.decode(self.device.store.slots["custom"])
        self.assertEqual((document["note"], document["written_by"], document["serial"]), ("for the school", "desktop", "SM-5"))
        self.press(self.panel._save)
        self.assertIn("version 2", self.panel.status_var.get())

    def test_save_without_a_profile_says_so_and_asks_nothing(self):
        self.messagebox.answer = False
        self.panel._save()
        self.assertIn("no calibration profile", self.panel.status_var.get())

    def test_declining_the_question_writes_nothing(self):
        calibration.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        calibration.profile_path("m1").write_text(__import__("json").dumps(demo_profile(20, 20)), encoding="utf-8")
        self.messagebox.answer = False
        self.panel._save()
        self.assertIsNone(self.device.store.slots["custom"])
        self.messagebox.answer = True

    def test_use_replaces_the_calibration_through_the_apps_normal_load(self):
        self.device.store.slots["custom"] = passport.encode(passport.build("custom", "SM-5", "MC266", demo_profile(20, 20), None, 4, "Lab"))
        self.device.publish_summary()
        self.press(lambda: self.panel._use("custom"))
        self.assertEqual(self.panel.status_var.get(), "Calibration replaced with the mat's custom passport.")
        self.assertTrue(calibration.load_profile("m1"))

    def test_use_of_an_empty_slot_or_another_size_is_told_in_words(self):
        self.press(lambda: self.panel._use("factory"))
        self.assertIn("nothing", self.panel.status_var.get())
        self.device.store.slots["custom"] = passport.encode(passport.build("custom", "SM-5", "MC266", demo_profile(10, 10)))
        self.device.publish_summary()
        self.press(lambda: self.panel._use("custom"))
        self.assertIn("10x10", self.panel.status_var.get())

    def test_a_broker_that_cannot_be_reached_is_told_in_words(self):
        with mock.patch.object(self.module.passport_sync, "connect", lambda *a, **k: (False, "cannot reach the MQTT broker at x:1")):
            self.press(self.panel._show)
        self.assertEqual(self.panel.status_var.get(), "cannot reach the MQTT broker at x:1")


if __name__ == "__main__":
    unittest.main()
