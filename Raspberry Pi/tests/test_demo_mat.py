"""Demo mat: publish_demo_mat replay with a fake client, and demo- chip ids accepted by the MQTT topic handling."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import publish_demo_mat as demo
from general import parse_frame_text_with_reason
from processing.recording import load_session
from sources import mqtt_source
from sources.mqtt_source import MqttSource, parse_meta

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "seat_take1.json"


class FakeClient:
    def __init__(self):
        self.sent = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.sent.append((topic, payload, retain))


class PublishDemoMatTest(unittest.TestCase):
    def setUp(self):
        self.frames, self.times = load_session(SAMPLE, with_timestamps=True)
        self.client, self.sleeps = FakeClient(), []

    def run_once(self, **kwargs):
        return demo.replay(self.client, "demo-take1", self.frames, self.times, loop=False,
                           sleep=self.sleeps.append, **kwargs)

    def test_meta_and_status_retained_frames_not(self):
        self.assertEqual(self.run_once(), len(self.frames))
        meta, status, *frames = self.client.sent
        self.assertEqual(meta, ("smartmat/demo-take1/meta", "demo-take1,20,20,255,MC266,343,358", True))
        self.assertEqual(status, ("smartmat/demo-take1/status", "online", True))
        self.assertEqual(len(frames), len(self.frames))
        self.assertTrue(all(topic == "smartmat/demo-take1/frame" and not retain for topic, _, retain in frames))

    def test_values_converted_to_counts(self):
        self.assertEqual(demo.frame_payload(np.array([[0.0, 1000.0], [500.0, 1.0]])), "0,255,128,0")
        self.run_once()
        grid, reason = parse_frame_text_with_reason(self.client.sent[2][1], 255, (20, 20))
        self.assertIsNone(reason)
        self.assertEqual(grid.shape, (20, 20))
        self.assertGreater(grid.max(), 0)

    def test_timing_follows_recording_and_speed(self):
        self.run_once(speed=2.0)
        self.assertAlmostEqual(sum(self.sleeps[:-1]), (self.times[-1] - self.times[0]) / 2.0)

    def test_chip_id_option(self):
        demo.replay(self.client, "demo-x", self.frames[:2], self.times[:2], loop=False, sleep=lambda _s: None)
        self.assertEqual(self.client.sent[0][0], "smartmat/demo-x/meta")


class DemoChipIdTest(unittest.TestCase):
    def test_parse_meta_accepts_hyphen_but_not_wildcards(self):
        self.assertEqual(parse_meta("demo-take1,20,20,255,MC266,343,358")[:4], ("demo-take1", 20, 20, 255))
        for bad in ("a+b,2,2", "#,2,2", "a/b,2,2", "-,2,2x"):
            self.assertIsNone(parse_meta(bad), bad)

    def test_source_reads_demo_meta_and_status(self):
        with mock.patch.object(mqtt_source, "mqtt"), mock.patch.object(mqtt_source.app_settings, "load", return_value={}):
            source = MqttSource()
        send = lambda topic, text: source._on_message(None, None, SimpleNamespace(
            topic=topic, payload=text.encode(), retain=True))
        send("smartmat/demo-take1/meta", "demo-take1,20,20,255,MC266,343,358")
        send("smartmat/demo-take1/status", "online")
        self.assertEqual(source.mats["demo-take1"], (20, 20))
        self.assertEqual(source.status["demo-take1"], "online")


if __name__ == "__main__":
    unittest.main()
