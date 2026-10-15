// Host test for frame_mailbox.h: pio test -e native
#include <unity.h>

#include <cstdint>
#include <cstring>

#include "frame_mailbox.h"

void test_empty_mailbox_gives_nothing() {
  FrameMailbox m;
  uint8_t out[400];
  uint32_t last = 0;
  TEST_ASSERT_FALSE(m.take_if_new(last, out));
}

void test_take_once_per_put() {
  FrameMailbox m;
  uint8_t f[400], out[400];
  uint32_t last = 0;
  memset(f, 7, sizeof(f));
  m.put(f);
  TEST_ASSERT_TRUE(m.take_if_new(last, out));
  TEST_ASSERT_EQUAL(7, out[399]);
  TEST_ASSERT_FALSE(m.take_if_new(last, out)); // same sequence: not published twice
}

void test_latest_wins() {
  FrameMailbox m;
  uint8_t f[400], out[400];
  uint32_t last = 0;
  memset(f, 1, sizeof(f)); m.put(f);
  memset(f, 2, sizeof(f)); m.put(f); // reader was busy: the older frame is overwritten
  TEST_ASSERT_TRUE(m.take_if_new(last, out));
  TEST_ASSERT_EQUAL(2, out[0]);
  TEST_ASSERT_EQUAL(2u, last);
  TEST_ASSERT_FALSE(m.take_if_new(last, out));
}

void test_frame_csv() {
  uint8_t f[400] = {};
  f[0] = 255; f[1] = 10; f[2] = 9; f[399] = 100;
  char out[400 * 4];
  format_frame_csv(f, 400, out);
  TEST_ASSERT_EQUAL_STRING_LEN("255,10,9,0,", out, 11);
  TEST_ASSERT_EQUAL_STRING(",0,100", out + strlen(out) - 6);
  int commas = 0;
  for (const char* c = out; *c; ++c) commas += *c == ',';
  TEST_ASSERT_EQUAL(399, commas);
  memset(f, 255, sizeof(f)); // worst case fits the buffer exactly
  format_frame_csv(f, 400, out);
  TEST_ASSERT_EQUAL(400 * 4 - 1, strlen(out));
}

void test_meta() {
  char out[64];
  TEST_ASSERT_TRUE(format_meta(out, sizeof(out), "a1b2c3d4e5f6", 20, 20, 255, "MC266", 343, 358));
  TEST_ASSERT_EQUAL_STRING("a1b2c3d4e5f6,20,20,255,MC266,343,358", out);
  TEST_ASSERT_TRUE(format_meta(out, sizeof(out), "x", 1, 1, 1, "Mat_2-b", 1, 1));
  TEST_ASSERT_FALSE(format_meta(out, sizeof(out), "x", 20, 20, 255, "MC 266", 343, 358));
  TEST_ASSERT_FALSE(format_meta(out, sizeof(out), "x", 20, 20, 255, "MC,266", 343, 358));
  TEST_ASSERT_FALSE(format_meta(out, sizeof(out), "x", 20, 20, 255, "", 343, 358));
  TEST_ASSERT_FALSE(format_meta(out, sizeof(out), "x", 20, 20, 255, "MC266", 0, 358));
  TEST_ASSERT_FALSE(format_meta(out, 10, "a1b2c3d4e5f6", 20, 20, 255, "MC266", 343, 358)); // truncated
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_empty_mailbox_gives_nothing);
  RUN_TEST(test_take_once_per_put);
  RUN_TEST(test_latest_wins);
  RUN_TEST(test_frame_csv);
  RUN_TEST(test_meta);
  return UNITY_END();
}

void setUp() {}
void tearDown() {}
