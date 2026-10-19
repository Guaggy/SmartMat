"""The desktop's passport logic against the Python stand-in for the firmware (in-process bus, no display, no broker)."""

import unittest

from matlink.passport_fake import FakePassportDevice
from matlink.passport_link import LoopbackBus, PassportLink
from client import passport_sync
from processing import passport
from server.__main__ import demo_profile


class SyncTests(unittest.TestCase):
    def setUp(self):
        bus = LoopbackBus()
        self.device = FakePassportDevice(bus.transport(), "m1", "SM-3", "key")
        self.link = PassportLink(bus.transport(), 0.3)

    def test_an_empty_mat(self):
        ok, lines = passport_sync.slot_lines(self.link, "m1")
        self.assertEqual((ok, lines), (True, ["Serial number: SM-3", "Factory: empty", "Custom: empty"]))

    def test_a_silent_mat_gets_a_sentence(self):
        ok, text = passport_sync.slot_lines(self.link, "nobody")
        self.assertFalse(ok)
        self.assertIn("passport", text)

    def test_save_then_describe_then_fetch_with_rising_versions(self):
        profile = demo_profile(20, 20)
        self.assertEqual(passport_sync.save_custom(self.link, "m1", profile, "Ola", "school")[1]["version"], 1)
        self.assertEqual(passport_sync.save_custom(self.link, "m1", profile, "Ola", "again")[1]["version"], 2)
        lines = passport_sync.slot_lines(self.link, "m1")[1]
        self.assertRegex(lines[2], r"^Custom: custom v2 by Ola.*\(again\)$")
        ok, document = passport_sync.fetch(self.link, "m1", "custom", (20, 20))
        self.assertTrue(ok)
        self.assertEqual(document["profile"], profile)
        self.assertEqual(document["serial"], "SM-3")

    def test_fetch_refuses_another_size_or_an_empty_slot(self):
        passport_sync.save_custom(self.link, "m1", demo_profile(20, 20))
        ok, text = passport_sync.fetch(self.link, "m1", "custom", (10, 10))
        self.assertFalse(ok)
        self.assertIn("20x20", text)
        self.assertFalse(passport_sync.fetch(self.link, "m1", "factory", (20, 20))[0])

    def test_save_without_a_profile_is_a_sentence_not_a_crash(self):
        ok, text = passport_sync.save_custom(self.link, "m1", None)
        self.assertFalse(ok)
        self.assertIn("profile", text)

    def test_a_damaged_slot_is_listed_as_damaged(self):
        self.device.store.slots["custom"] = passport.MAGIC + b"garbage!"
        self.device.publish_summary()
        self.assertIn("damaged", passport_sync.slot_lines(self.link, "m1")[1][2])


if __name__ == "__main__":
    unittest.main()
