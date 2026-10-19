"""PassportLink against the Python stand-in for the firmware's MQTT behaviour, over an in-process bus."""

import unittest

from passport_fake import FakePassportDevice
from passport_link import LoopbackBus, PassportError, PassportLink
from processing import passport
from server.__main__ import demo_profile

KEY = "s3rv1ce"
CHIP = "aabbccddeeff"


def blob_of(slot="custom", **kw):
    return passport.encode(passport.build(slot, "SM-1", "MC266", demo_profile(20, 20), t=1.0, **kw))


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.bus = LoopbackBus()
        self.device = FakePassportDevice(self.bus.transport(), CHIP, serial="SM-1", service_key=KEY)
        self.link = PassportLink(self.bus.transport(), timeout=0.3)

    def test_summary_is_the_retained_message(self):
        self.assertEqual(self.link.summary(CHIP), {"serial": "SM-1", "factory": None, "custom": None, "max": 16384})
        self.assertIsNone(PassportLink(self.bus.transport(), timeout=0.1).summary("000000000000"))

    def test_write_then_read_the_custom_slot(self):
        blob = blob_of()
        self.link.write(CHIP, "custom", blob)
        document, back = self.link.read(CHIP, "custom")
        self.assertEqual((back, document["slot"]), (blob, "custom"))
        self.assertEqual(self.link.summary(CHIP)["custom"], {"bytes": len(blob), "crc": passport.crc_hex(blob)})

    def test_the_factory_slot_needs_the_key(self):
        blob = blob_of("factory")
        with self.assertRaisesRegex(PassportError, "service key"):
            self.link.write(CHIP, "factory", blob, "wrong")
        self.link.write(CHIP, "factory", blob, KEY)
        self.assertEqual(self.device.store.slots["factory"], blob)

    def test_reading_an_empty_slot_says_so(self):
        with self.assertRaisesRegex(PassportError, "nothing"):
            self.link.read(CHIP, "custom")

    def test_a_damaged_slot_is_reported_not_returned(self):
        self.device.store.slots["custom"] = passport.MAGIC + b"garbage!"
        with self.assertRaisesRegex(PassportError, "damaged"):
            self.link.read(CHIP, "custom")

    def test_clear_only_touches_the_custom_slot(self):
        self.link.write(CHIP, "custom", blob_of())
        self.link.clear_custom(CHIP)
        self.assertIsNone(self.device.store.slots["custom"])

    def test_serial_needs_the_key(self):
        with self.assertRaises(PassportError):
            self.link.set_serial(CHIP, "SM-9", "wrong")
        self.link.set_serial(CHIP, "SM-9", KEY)
        self.assertEqual(self.link.summary(CHIP)["serial"], "SM-9")

    def test_no_device_means_a_timeout_sentence(self):
        with self.assertRaisesRegex(PassportError, "did not answer"):
            self.link.write("000000000000", "custom", blob_of())

    def test_a_mat_that_stored_other_bytes_is_caught(self):
        original = self.device.store.put
        self.device.store.put = lambda slot, payload: original(slot, payload[:-1] if slot == "custom" else payload)
        with self.assertRaisesRegex(PassportError, "different"):
            self.link.write(CHIP, "custom", blob_of())

    def test_bad_slot_name_is_refused_locally(self):
        with self.assertRaisesRegex(PassportError, "slot"):
            self.link.write(CHIP, "elsewhere", blob_of())


if __name__ == "__main__":
    unittest.main()
