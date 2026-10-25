"""The mat passport on the server: REST routes, adopting a slot, writing the custom slot, zero-touch adoption of a new mat."""

import unittest

from matlink.passport_fake import FakePassportDevice
from matlink.passport_link import LoopbackBus, PassportLink
from processing import calibration, passport
from server.app import create_app
from server.passports import PassportService, same_calibration
from server.settings import Settings
from server.__main__ import demo_profile

from test_server_app import ADMIN, NURSE, ApiTests

KEY = "k3y"


def blob_of(slot="custom", analysis=None, version=1, rows=20, cols=20, **profile_changes):
    profile = dict(demo_profile(rows, cols), **profile_changes)
    return passport.encode(passport.build(slot, "SM-7", "MC266", profile, analysis, version, "Lab", "calibrated", 5000.0))


class PassportApiTests(ApiTests):
    def setUp(self):
        super().setUp()
        self.settings = Settings(self.store)
        self.bus = LoopbackBus()
        self.device = FakePassportDevice(self.bus.transport(), "m1", serial="SM-7", service_key=KEY)
        link = PassportLink(self.bus.transport(), timeout=0.3)
        self.service = PassportService(lambda: link, self.store, self.settings, self.engines, lambda: self.now)
        self.client = create_app(self.store, self.alerts, self.engines, clock=lambda: self.now, settings=self.settings,
                                 passports=self.service).test_client()
        self.make_users()

    def give(self, **slots):
        """Put bytes in the device's slots as if written earlier; the device then (re)publishes its summary"""
        self.device.store.slots.update(slots)
        self.device.publish_summary()

    def test_without_support_the_routes_say_so(self):
        plain = create_app(self.store, self.alerts, self.engines, clock=lambda: self.now).test_client()
        self.assertEqual(plain.get("/api/mats/m1/passport").status_code, 501)

    def test_status_describes_both_slots(self):
        self.give(custom=blob_of())
        reply = self.client.get("/api/mats/m1/passport")
        self.assertEqual(reply.status_code, 200)
        data = reply.get_json()
        self.assertEqual((data["serial"], data["slots"]["factory"]), ("SM-7", None))
        custom = data["slots"]["custom"]
        self.assertRegex(custom["info"], r"^custom v1 by Lab")
        self.assertEqual((custom["note"], custom["has_analysis"], custom["same_as_now"]), ("calibrated", False, False))
        self.assertEqual(self.client.get("/api/mats/nope/passport").status_code, 404)

    def test_status_of_a_mat_that_is_silent_is_a_bad_gateway(self):
        self.engines["m2"] = self.engines["m1"]
        self.assertEqual(self.client.get("/api/mats/m2/passport").status_code, 502)

    def test_adopting_a_slot_sets_the_calibration_and_logs_it(self):
        # build the expected profile once, before anything runs: demo_profile() reads the process-wide grid size in
        # config, so building it a second time at the end could (rarely, in a full run) see another test's value
        expected = demo_profile(20, 20)
        self.give(custom=blob_of(**expected))
        self.assertEqual(self.post("/api/mats/m1/passport/adopt", slot="custom").status_code, 401)
        self.assertEqual(self.post("/api/mats/m1/passport/adopt", slot="custom", pin=NURSE).status_code, 403)     # admin only
        self.assertEqual(self.post("/api/mats/m1/passport/adopt", slot="x", pin=ADMIN).status_code, 400)
        reply = self.post("/api/mats/m1/passport/adopt", slot="custom", pin=ADMIN)
        self.assertEqual(reply.status_code, 200, reply.get_json())
        self.assertEqual(self.engines["m1"].profile_version, 1)
        self.assertTrue(same_calibration(self.engines["m1"].profile, expected))
        self.assertTrue(calibration.load_profile("m1"))
        self.assertIn(("passport adopted", "Admin"), self.kinds("m1"))
        self.assertTrue(self.client.get("/api/mats/m1/passport").get_json()["slots"]["custom"]["same_as_now"])

    def test_adopting_a_passport_of_another_size_is_refused_and_changes_nothing(self):
        self.give(custom=blob_of(rows=10, cols=10))
        reply = self.post("/api/mats/m1/passport/adopt", slot="custom", pin=ADMIN)
        self.assertEqual(reply.status_code, 502)
        self.assertIn("another size", reply.get_json()["error"])
        self.assertIsNone(self.engines["m1"].profile)
        self.assertNotIn("passport adopted", [k for k, _ in self.kinds("m1")])

    def test_the_analysis_settings_in_a_passport_become_the_mats_own_layer(self):
        self.settings.update({"near_percent": 70}, scope="m1", user="x")      # an old override the passport does not mention
        self.give(custom=blob_of(analysis={"alert_high_hold_s": 45}))
        self.assertEqual(self.post("/api/mats/m1/passport/adopt", slot="custom", pin=ADMIN).status_code, 200)
        self.assertEqual(self.settings.layer("m1"), {"alert_high_hold_s": 45})
        self.assertEqual(self.settings.history("m1")[0]["user"], "Admin")

    def test_a_passport_with_a_bad_analysis_key_changes_nothing_about_settings(self):
        self.give(custom=blob_of(analysis={"no_such_setting": 1}))
        reply = self.post("/api/mats/m1/passport/adopt", slot="custom", pin=ADMIN)
        self.assertEqual(reply.status_code, 502)
        self.assertEqual(self.settings.layer("m1"), {})

    def test_write_saves_the_current_calibration_with_a_rising_version(self):
        self.assertEqual(self.post("/api/mats/m1/passport/write", pin=ADMIN).status_code, 502)       # no calibration yet
        self.assertEqual(self.put("/api/mats/m1/profile", pin=ADMIN, profile=demo_profile(20, 20)).status_code, 200)
        self.settings.update({"alert_high_hold_s": 30}, scope="m1", user="x")
        reply = self.post("/api/mats/m1/passport/write", pin=ADMIN, note="before shipping")
        self.assertEqual((reply.status_code, reply.get_json()["version"]), (200, 1))
        document = passport.decode(self.device.store.slots["custom"])
        self.assertEqual((document["note"], document["written_by"], document["serial"], document["analysis"]),
                         ("before shipping", "Admin", "SM-7", {"alert_high_hold_s": 30}))
        self.assertEqual(self.post("/api/mats/m1/passport/write", pin=ADMIN).get_json()["version"], 2)
        self.assertIn(("passport written", "Admin"), self.kinds("m1"))
        self.assertEqual(self.post("/api/mats/m1/passport/write", pin=NURSE).status_code, 403)

    def test_zero_touch_a_new_mat_takes_its_passport_custom_before_factory(self):
        self.give(factory=blob_of("factory"), custom=blob_of(version=4, analysis={"alert_offline_s": 90}))
        self.assertEqual(self.service.auto_adopt("m1"), "custom")
        self.assertEqual(self.settings.layer("m1"), {"alert_offline_s": 90})
        self.assertIn(("passport adopted", "system"), self.kinds("m1"))
        self.assertIsNone(self.service.auto_adopt("m1"))        # once

    def test_zero_touch_leaves_a_calibrated_mat_alone(self):
        self.put("/api/mats/m1/profile", pin=ADMIN, profile=demo_profile(20, 20))
        self.give(custom=blob_of(version=9))
        self.assertIsNone(self.service.auto_adopt("m1"))
        self.assertEqual(self.engines["m1"].profile_version, 1)

    def test_zero_touch_with_a_bad_passport_logs_why_and_carries_on(self):
        self.give(custom=passport.MAGIC + b"garbage!")
        self.assertIsNone(self.service.auto_adopt("m1"))
        self.assertIn(("passport not adopted", "system"), self.kinds("m1"))


if __name__ == "__main__":
    unittest.main()
