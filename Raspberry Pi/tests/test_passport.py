"""The mat passport: the document and its bytes, and the rules of a device that stores it (passport_device.py, the model of the
firmware). The expected texts here are also hard-coded in the firmware's host test (ESP32_China/test/test_passport)."""

import json
import random
import unittest
import zlib

from passport_device import DeviceStore, ack, split_key
from processing import passport
from processing.calibration import IndividualCalibration
from server.__main__ import demo_profile

KEY = "s3rv1ce-key"


def blob_of(slot="custom", **kw):
    return passport.encode(passport.build(slot, kw.pop("serial", "SM-0001"), "MC266", demo_profile(20, 20), t=1000.0, **kw))


class DocumentTests(unittest.TestCase):
    def test_crc32_matches_the_standard_check_value(self):
        self.assertEqual(passport.crc_hex(b"123456789"), "cbf43926")     # the same vector is in the firmware's test
        self.assertEqual(passport.crc_hex(b""), "00000000")

    def test_a_document_survives_encode_and_decode(self):
        analysis = {"hotspots.activate_kpa": 28.0, "indices": None}
        doc = passport.build("custom", "SM-0001", "MC266", demo_profile(20, 20), analysis, version=3, by="Admin", note="soft cushion", t=1000.0)
        back = passport.decode(passport.encode(doc))
        self.assertEqual(back, doc)
        self.assertEqual((back["slot"], back["version"], back["written_by"], back["analysis"]["hotspots.activate_kpa"]), ("custom", 3, "Admin", 28.0))
        self.assertEqual(passport.keep(back)["profile"], doc["profile"])

    def test_the_same_document_is_always_the_same_bytes(self):
        self.assertEqual(blob_of(), blob_of())
        self.assertEqual(passport.crc_hex(blob_of()), passport.crc_hex(blob_of()))
        self.assertTrue(blob_of().startswith(passport.MAGIC))

    def test_a_per_cell_profile_fits_a_slot_with_room_to_spare(self):
        profile = demo_profile(20, 20)
        individual = IndividualCalibration.default().to_dict()
        rng = random.Random(1)
        for cell in individual["cells"]:       # every cell different, so compression cannot collapse them
            cell["points"] = [[round(v * rng.uniform(0.9, 1.1), 4) for v in point] for point in cell["points"]]
        profile["individual"] = individual
        blob = passport.encode(passport.build("custom", "SM-1", "MC266", profile))
        self.assertLess(len(blob), passport.MAX_BYTES // 2)
        self.assertEqual(passport.decode(blob)["profile"]["individual"], individual)

    def test_too_big_is_refused_when_encoding(self):
        profile = demo_profile(20, 20)
        rng = random.Random(2)
        profile["roi"] = [rng.random() for _ in range(6000)]     # random numbers do not compress
        with self.assertRaisesRegex(ValueError, "a slot holds"):
            passport.encode(passport.build("custom", "SM-1", "MC266", profile))

    def test_build_refuses_what_could_not_be_read_back(self):
        profile = demo_profile(20, 20)
        for kwargs, text in (({"slot": "nope"}, "slot"), ({"profile": {"format": "x"}}, "profile"), ({"profile": dict(profile, grid_shape=[0, 3])}, "grid_shape"),
                             ({"analysis": [1]}, "analysis"), ({"version": 0}, "version"), ({"version": True}, "version")):
            args = dict(slot="custom", serial="S", model="M", profile=profile)
            args.update(kwargs)
            with self.assertRaisesRegex(ValueError, text):
                passport.build(**args)

    def test_decode_says_what_is_wrong(self):
        good = blob_of()
        cases = [(b"", "too short"), (b"abc", "too short"), (b"XXXX" + good[4:], "wrong start"),
                 (good[:4] + b"not zlib at all", "damaged"), (good[:-3], "damaged"),
                 (passport.MAGIC + zlib.compress(b"[1, 2]"), "not a smartmat_mat_passport_v1"),
                 (passport.MAGIC + zlib.compress(b'{"format": "smartmat_mat_passport_v1"}'), "no slot"),
                 (passport.MAGIC + zlib.compress(b"\xff\xfe"), "damaged"), (good + b"x" * passport.MAX_BYTES, "larger")]
        for blob, text in cases:
            with self.assertRaisesRegex(ValueError, text, msg=blob[:20]):
                passport.decode(blob)
        doc = passport.decode(good)
        doc["slot"] = "elsewhere"
        with self.assertRaisesRegex(ValueError, "unknown slot"):
            passport.decode(passport.MAGIC + zlib.compress(passport.canonical(doc)))

    def test_a_flipped_byte_is_caught_by_the_crc_and_usually_by_decode(self):
        good = blob_of()
        bad = bytearray(good)
        bad[len(bad) // 2] ^= 0x01
        self.assertNotEqual(passport.crc_hex(bytes(bad)), passport.crc_hex(good))

    def test_describe_is_a_line_for_people(self):
        doc = passport.build("custom", "SM-1", "MC266", demo_profile(20, 20), version=2, by="Admin", note="5 kg", t=0)
        self.assertRegex(passport.describe(doc), r"^custom v2 by Admin, \d{4}-\d\d-\d\d \d\d:\d\d \(5 kg\)$")
        self.assertEqual(passport.describe(dict(doc, written_by="", note="")).split(",")[0], "custom v2")


class DeviceTests(unittest.TestCase):
    """The texts below are the firmware's, character for character"""

    def device(self, **kw):
        return DeviceStore(serial="SM-0001", service_key=KEY, **kw)

    def test_an_empty_device_summary(self):
        self.assertEqual(self.device().summary(), '{"serial":"SM-0001","factory":null,"custom":null,"max":16384}')

    def test_the_summary_after_writes_names_size_and_crc(self):
        device, blob = self.device(), b"SMP1\x78\x9c\x03\x00\x00\x00\x00\x01"
        self.assertEqual(device.put("custom", blob), '{"op":"put","slot":"custom","ok":true,"bytes":12,"crc":"%s"}' % passport.crc_hex(blob))
        self.assertEqual(device.summary(), '{"serial":"SM-0001","factory":null,"custom":{"bytes":12,"crc":"%s"},"max":16384}' % passport.crc_hex(blob))

    def test_the_custom_slot_takes_a_passport_and_gives_it_back(self):
        device, blob = self.device(), blob_of()
        reply = json.loads(device.put("custom", blob))
        self.assertEqual((reply["ok"], reply["bytes"], reply["crc"]), (True, len(blob), passport.crc_hex(blob)))
        self.assertEqual(device.get("custom"), (blob, None))
        self.assertEqual(passport.decode(device.get("custom")[0])["slot"], "custom")

    def test_what_the_custom_slot_refuses(self):
        device = self.device()
        self.assertEqual(device.put("custom", b""), '{"op":"put","slot":"custom","ok":false,"err":"empty"}')
        self.assertEqual(device.put("custom", b"XXXXabc"), '{"op":"put","slot":"custom","ok":false,"err":"bad_magic"}')
        self.assertEqual(device.put("custom", passport.MAGIC + b"x" * passport.MAX_BYTES), '{"op":"put","slot":"custom","ok":false,"err":"too_big"}')
        self.assertEqual(device.put("elsewhere", blob_of()), '{"op":"put","slot":"elsewhere","ok":false,"err":"slot"}')
        self.assertEqual(device.slots, {"factory": None, "custom": None})
        exactly = passport.MAGIC + b"x" * (passport.MAX_BYTES - len(passport.MAGIC))
        self.assertTrue(json.loads(device.put("custom", exactly))["ok"])          # exactly the limit is fine

    def test_the_factory_slot_needs_the_service_key(self):
        device, blob = self.device(), blob_of("factory")
        locked = '{"op":"put","slot":"factory","ok":false,"err":"locked"}'
        self.assertEqual(device.put("factory", blob), locked)                                   # no key header
        self.assertEqual(device.put("factory", b"KEY:wrong\n" + blob), locked)
        self.assertEqual(device.put("factory", b"KEY:" + KEY.encode() + b"x\n" + blob), locked)
        self.assertEqual(device.put("factory", b"KEY:" + KEY.encode() + blob), locked)           # no newline: no header
        self.assertIsNone(device.slots["factory"])
        self.assertTrue(json.loads(device.put("factory", b"KEY:" + KEY.encode() + b"\n" + blob))["ok"])
        self.assertEqual(device.slots["factory"], blob)                                         # the key line is not stored
        self.assertEqual(device.put("factory", blob), locked)                                   # and it stays protected

    def test_a_device_without_a_service_key_has_no_writable_factory_slot(self):
        device = DeviceStore(serial="S", service_key="")
        self.assertEqual(json.loads(device.put("factory", b"KEY:\n" + blob_of("factory")))["err"], "locked")
        self.assertEqual(json.loads(device.set_serial(b"KEY:\nSM-9"))["err"], "locked")

    def test_the_factory_blob_is_still_checked_after_the_key(self):
        device = self.device()
        header = b"KEY:" + KEY.encode() + b"\n"
        self.assertEqual(json.loads(device.put("factory", header))["err"], "empty")
        self.assertEqual(json.loads(device.put("factory", header + b"nope"))["err"], "bad_magic")

    def test_clear_only_clears_the_custom_slot(self):
        device = self.device(slots={"factory": blob_of("factory"), "custom": blob_of()})
        self.assertEqual(device.clear(b"factory"), '{"op":"clear","slot":"factory","ok":false,"err":"locked"}')
        self.assertEqual(device.clear(b"other"), '{"op":"clear","slot":"other","ok":false,"err":"slot"}')
        self.assertIsNotNone(device.slots["factory"])
        self.assertEqual(device.clear(b"custom"), '{"op":"clear","slot":"custom","ok":true}')
        self.assertIsNone(device.slots["custom"])
        self.assertIsNotNone(device.slots["factory"])

    def test_get_of_a_missing_or_unknown_slot_answers_with_an_error(self):
        device = self.device()
        self.assertEqual(device.get("custom"), (None, '{"op":"get","slot":"custom","ok":false,"err":"empty"}'))
        self.assertEqual(device.get("x"), (None, '{"op":"get","slot":"x","ok":false,"err":"slot"}'))

    def test_the_serial_is_set_with_the_key_and_must_be_plain(self):
        device = DeviceStore(service_key=KEY)
        self.assertEqual(device.set_serial(b"SM-9"), '{"op":"serial","slot":"","ok":false,"err":"locked"}')
        self.assertEqual(device.set_serial(b"KEY:" + KEY.encode() + b"\nSM-0042"), '{"op":"serial","slot":"","ok":true}')
        self.assertEqual(device.serial, "SM-0042")
        for bad in (b"", b"has space", b"x" * 25, b"quo\"te", "ø".encode()):
            self.assertEqual(json.loads(device.set_serial(b"KEY:" + KEY.encode() + b"\n" + bad))["err"], "serial", bad)
        self.assertEqual(device.serial, "SM-0042")

    def test_split_key(self):
        self.assertEqual(split_key(b"KEY:abc\nrest\nmore"), (b"abc", b"rest\nmore"))
        self.assertEqual(split_key(b"KEY:\n"), (b"", b""))
        for bad in (b"", b"abc", b"KEY:abc", b"key:abc\nx"):
            self.assertIsNone(split_key(bad))

    def test_ack_texts(self):
        self.assertEqual(ack("put", "custom", False, "locked"), '{"op":"put","slot":"custom","ok":false,"err":"locked"}')
        self.assertEqual(ack("clear", "custom", True), '{"op":"clear","slot":"custom","ok":true}')


class FirmwareCopiesTests(unittest.TestCase):
    def test_both_boards_carry_the_same_passport_code(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        for name in ("mat_passport.h", "passport_service.h"):
            self.assertEqual((root / "ESP32_China" / "src" / name).read_bytes(), (root / "ESP32_Resistive" / "src" / name).read_bytes(),
                             f"{name} differs between ESP32_China and ESP32_Resistive: copy one over the other")


if __name__ == "__main__":
    unittest.main()
