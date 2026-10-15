// Host test for frame_accumulator.h: pio test -e native
#include <unity.h>

#include <cstdint>
#include <cstring>

#include "frame_accumulator.h"

static void fill(uint8_t* f, uint8_t v) { memset(f, v, FrameAccumulator::cells); }

void test_mean_of_frames() {
  FrameAccumulator a;
  uint8_t f[400], out[400];
  fill(f, 10); a.add(f);
  fill(f, 20); a.add(f);
  fill(f, 30); a.add(f);
  TEST_ASSERT_EQUAL(3, a.count());
  TEST_ASSERT_TRUE(a.take_mean(out));
  TEST_ASSERT_EQUAL(20, out[0]);
  TEST_ASSERT_EQUAL(20, out[399]);
}

void test_rounds_to_nearest() {
  FrameAccumulator a;
  uint8_t f[400], out[400];
  fill(f, 1); a.add(f);
  fill(f, 2); a.add(f);          // mean 1.5 -> 2
  a.take_mean(out);
  TEST_ASSERT_EQUAL(2, out[0]);
  fill(f, 0); a.add(f); a.add(f);
  fill(f, 1); a.add(f);          // mean 0.33 -> 0
  a.take_mean(out);
  TEST_ASSERT_EQUAL(0, out[0]);
}

void test_count_resets_after_take() {
  FrameAccumulator a;
  uint8_t f[400], out[400];
  fill(f, 100); a.add(f);
  TEST_ASSERT_TRUE(a.take_mean(out));
  TEST_ASSERT_EQUAL(0, a.count());
  out[0] = 77;
  TEST_ASSERT_FALSE(a.take_mean(out));  // empty window: nothing to publish, out untouched
  TEST_ASSERT_EQUAL(77, out[0]);
  fill(f, 50); a.add(f);                // the old sums must not leak into the new window
  a.take_mean(out);
  TEST_ASSERT_EQUAL(50, out[0]);
}

void test_per_cell_values_and_saturation() {
  FrameAccumulator a;
  uint8_t f[400], out[400];
  for (int n = 0; n < 1000; ++n) {  // more than max_count: extra frames are ignored, no overflow
    fill(f, 255);
    f[5] = 0;
    a.add(f);
  }
  TEST_ASSERT_EQUAL(FrameAccumulator::max_count, a.count());
  a.take_mean(out);
  TEST_ASSERT_EQUAL(255, out[0]);
  TEST_ASSERT_EQUAL(0, out[5]);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_mean_of_frames);
  RUN_TEST(test_rounds_to_nearest);
  RUN_TEST(test_count_resets_after_take);
  RUN_TEST(test_per_cell_values_and_saturation);
  return UNITY_END();
}

void setUp() {}
void tearDown() {}
