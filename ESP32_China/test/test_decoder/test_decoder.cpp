// Host test for maxrays_decoder.h: pio test -e native (or g++, see README).
// Mirrors Raspberry Pi/tests/test_maxrays.py.
#include <unity.h>

#include <cstdint>
#include <cstring>
#include <vector>

#include "maxrays_decoder.h"

typedef std::vector<uint8_t> Bytes;

// 406-byte packet: A5 5A, big-endian declared length, 400 payload bytes, 2 trailer bytes.
// Payload bytes never equal A5/5A so nothing inside a packet can look like a header.
static Bytes make_packet(uint8_t seed, uint16_t declared = 0x0196) {
  Bytes p = {0xA5, 0x5A, static_cast<uint8_t>(declared >> 8), static_cast<uint8_t>(declared & 0xFF)};
  for (int i = 0; i < 400; ++i) p.push_back(static_cast<uint8_t>(1 + (seed + i) % 100));
  p.push_back(0x11);
  p.push_back(0x22);
  return p;
}

static void append(Bytes& dst, const Bytes& src) { dst.insert(dst.end(), src.begin(), src.end()); }

// Collects the first payload byte of each decoded frame (= seed + 1 for make_packet) and checks the rest.
struct Sink {
  std::vector<int> firsts;
  bool payload_ok = true;
  void operator()(const uint8_t* payload) {
    firsts.push_back(payload[0]);
    for (int i = 0; i < 400; ++i) {
      if (payload[i] != 1 + (payload[0] - 1 + i) % 100) payload_ok = false;
    }
  }
};

static void feed_all(MaxraysDecoder& d, Sink& s, const Bytes& data, size_t chunk) {
  for (size_t i = 0; i < data.size(); i += chunk) {
    const size_t n = data.size() - i < chunk ? data.size() - i : chunk;
    d.feed(data.data() + i, n, [&s](const uint8_t* p) { s(p); });
  }
}

void test_single_frame() {
  MaxraysDecoder d; Sink s;
  feed_all(d, s, make_packet(0), 1000);
  TEST_ASSERT_EQUAL(1, s.firsts.size());
  TEST_ASSERT_EQUAL(1, s.firsts[0]);
  TEST_ASSERT_TRUE(s.payload_ok);
  TEST_ASSERT_EQUAL(406, d.bytes_received);
  TEST_ASSERT_EQUAL(0, d.invalid_frames);
}

void test_chunked_delivery_two_frames() {
  MaxraysDecoder d; Sink s;
  Bytes data = make_packet(0);
  append(data, make_packet(10));
  feed_all(d, s, data, 17);
  TEST_ASSERT_EQUAL(2, s.firsts.size());
  TEST_ASSERT_EQUAL(1, s.firsts[0]);
  TEST_ASSERT_EQUAL(11, s.firsts[1]);
  TEST_ASSERT_TRUE(s.payload_ok);
  TEST_ASSERT_EQUAL(0, d.invalid_frames);
  TEST_ASSERT_EQUAL(0, d.bytes_discarded);
}

void test_resync_after_noise() {
  MaxraysDecoder d; Sink s;
  Bytes data = {0x00, 0x13, 0x5A, 0xA5, 0x00, 0x7F};  // includes a stray 5A and a stray A5
  append(data, make_packet(3));
  append(data, Bytes{0xEE, 0xEE, 0xEE});
  append(data, make_packet(4));
  feed_all(d, s, data, 17);
  TEST_ASSERT_EQUAL(2, s.firsts.size());
  TEST_ASSERT_EQUAL(4, s.firsts[0]);
  TEST_ASSERT_EQUAL(5, s.firsts[1]);
  TEST_ASSERT_TRUE(s.payload_ok);
}

void test_false_header_in_noise() {
  MaxraysDecoder d; Sink s;
  Bytes data = {0xA5, 0x5A, 0x00, 0x10, 0x42, 0x42};  // looks like a header but declared length is nonsense
  append(data, make_packet(7));
  feed_all(d, s, data, 17);
  TEST_ASSERT_EQUAL(1, s.firsts.size());
  TEST_ASSERT_EQUAL(8, s.firsts[0]);
  TEST_ASSERT_TRUE(s.payload_ok);
  TEST_ASSERT_TRUE(d.invalid_frames >= 1);
}

void test_lone_trailing_a5_kept_across_chunks() {
  MaxraysDecoder d; Sink s;
  Bytes p = make_packet(2);
  Bytes first = {0x01, 0x02, 0xA5};  // noise, then the first half of the header
  d.feed(first.data(), first.size(), [&s](const uint8_t* q) { s(q); });
  TEST_ASSERT_EQUAL(0, s.firsts.size());
  TEST_ASSERT_EQUAL(2, d.bytes_discarded);  // the lone A5 is not discarded
  d.feed(p.data() + 1, p.size() - 1, [&s](const uint8_t* q) { s(q); });  // 5A ...
  TEST_ASSERT_EQUAL(1, s.firsts.size());
  TEST_ASSERT_EQUAL(3, s.firsts[0]);
  TEST_ASSERT_TRUE(s.payload_ok);
}

void test_declared_length_plus_four() {
  MaxraysDecoder d; Sink s;
  Bytes data = make_packet(5, 0x0192);  // declared 402 + 4 = 406
  append(data, make_packet(6, 0x0192));
  feed_all(d, s, data, 17);
  TEST_ASSERT_EQUAL(2, s.firsts.size());
  TEST_ASSERT_EQUAL(0, d.invalid_frames);
}

void test_reset_drops_partial_packet() {
  MaxraysDecoder d; Sink s;
  Bytes p = make_packet(0);
  d.feed(p.data(), 200, [&s](const uint8_t* q) { s(q); });  // unplugged mid-packet
  d.reset();
  Bytes q = make_packet(9);
  d.feed(q.data(), q.size(), [&s](const uint8_t* r) { s(r); });
  TEST_ASSERT_EQUAL(1, s.firsts.size());
  TEST_ASSERT_EQUAL(10, s.firsts[0]);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_single_frame);
  RUN_TEST(test_chunked_delivery_two_frames);
  RUN_TEST(test_resync_after_noise);
  RUN_TEST(test_false_header_in_noise);
  RUN_TEST(test_lone_trailing_a5_kept_across_chunks);
  RUN_TEST(test_declared_length_plus_four);
  RUN_TEST(test_reset_drops_partial_packet);
  return UNITY_END();
}

void setUp() {}
void tearDown() {}
