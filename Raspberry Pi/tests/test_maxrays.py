import os
import unittest

import numpy as np

from sources.maxrays import MaxraysDecoder

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "maxrays_capture.bin")


def packet(values, trailer=b"\x12\x34"):
    payload = values.astype(np.uint8).tobytes()
    return b"\xA5\x5A" + (4 + len(payload) + len(trailer)).to_bytes(2, "big") + payload + trailer


class MaxraysDecoderTests(unittest.TestCase):
    def setUp(self):
        self.values = np.arange(400, dtype=np.uint16).astype(np.uint8).reshape(20, 20)
        self.pkt = packet(self.values)
        self.dec = MaxraysDecoder()

    def test_chunked_17_bytes(self):
        out = []
        for i in range(0, len(self.pkt), 17):
            out += self.dec.feed(self.pkt[i:i + 17])
        self.assertEqual(len(out), 1)
        np.testing.assert_array_equal(out[0], self.values)
        self.assertEqual(out[0].dtype, np.uint8)

    def test_resync_after_noise(self):
        out = self.dec.feed(b"noise-before-frame" + self.pkt)
        self.assertEqual(len(out), 1)
        np.testing.assert_array_equal(out[0], self.values)
        self.assertEqual(self.dec.stats.bytes_discarded, len(b"noise-before-frame"))

    def test_two_consecutive_frames(self):
        other = (self.values[::-1]).copy()
        out = self.dec.feed(self.pkt + packet(other) + b"\xA5")
        self.assertEqual(len(out), 2)
        np.testing.assert_array_equal(out[0], self.values)
        np.testing.assert_array_equal(out[1], other)
        self.assertEqual(self.dec.stats.frames_decoded, 2)

    def test_false_header_in_noise(self):
        out = self.dec.feed(b"\xA5\x5A\x00\x01" + b"x" * 10 + self.pkt)
        self.assertEqual(len(out), 1)
        np.testing.assert_array_equal(out[0], self.values)

    def test_false_header_counted_when_full_packet_buffered(self):
        # bogus header with an implausible declared length, followed by a full real packet
        out = self.dec.feed(b"\xA5\x5A\x00\x01" + b"\x00" * 500 + self.pkt)
        self.assertGreaterEqual(len(out), 1)
        self.assertGreaterEqual(self.dec.stats.invalid_frames, 1)

    def test_frame_split_across_feeds(self):
        self.assertEqual(self.dec.feed(self.pkt[:200]), [])
        out = self.dec.feed(self.pkt[200:])
        self.assertEqual(len(out), 1)
        np.testing.assert_array_equal(out[0], self.values)

    def test_lone_trailing_a5_is_kept(self):
        self.assertEqual(self.dec.feed(b"junk\xA5"), [])
        self.assertEqual(self.dec.stats.bytes_discarded, 4)
        out = self.dec.feed(self.pkt[1:])
        self.assertEqual(len(out), 1)
        np.testing.assert_array_equal(out[0], self.values)

    def test_trailer_that_looks_like_a_header(self):
        other = (self.values[::-1]).copy()
        out = self.dec.feed(packet(self.values, trailer=b"\xA5\x5A") + packet(other) + packet(self.values))
        self.assertEqual(len(out), 3)
        np.testing.assert_array_equal(out[1], other)

    def test_packet_with_lost_bytes_is_dropped_not_decoded(self):
        other = (self.values[::-1]).copy()
        out = self.dec.feed(self.pkt[:-10] + packet(other) + packet(self.values))
        self.assertEqual(len(out), 2)
        np.testing.assert_array_equal(out[0], other)
        np.testing.assert_array_equal(out[1], self.values)
        self.assertGreaterEqual(self.dec.stats.invalid_frames, 1)

    def test_four_trailer_bytes_in_small_chunks(self):
        # the real mat (seen on hardware): declared 406 but 4 trailer bytes, so each packet is 408 bytes long
        pkt = b"\xA5\x5A" + (406).to_bytes(2, "big") + self.values.tobytes() + b"\x01\x99\x01\x99"
        data, out = pkt * 5, []
        for i in range(0, len(data), 256):
            out += self.dec.feed(data[i:i + 256])
        self.assertGreaterEqual(len(out), 4)  # the last one may wait for the next header
        self.assertEqual(self.dec.stats.invalid_frames, 0)

    @unittest.skipUnless(os.path.exists(FIXTURE), "tests/fixtures/maxrays_capture.bin not present")
    def test_real_capture(self):
        with open(FIXTURE, "rb") as f:
            out = self.dec.feed(f.read())
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(self.dec.stats.invalid_frames, 0)


if __name__ == "__main__":
    unittest.main()
