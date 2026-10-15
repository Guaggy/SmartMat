#pragma once

// Averages every frame decoded inside one publish window (the mat streams ~60 Hz, we publish 10 fps).
// Header-only, no Arduino includes (so it also builds in the native host test).

#include <cstddef>
#include <cstdint>

class FrameAccumulator {
 public:
  static const size_t cells = 400;       // 20x20
  static const uint16_t max_count = 257; // 257 * 255 = 65535: the uint16 sums cannot overflow

  uint16_t count() const { return count_; }

  // Add one raw frame (cells values, 0-255). Frames beyond max_count in one window are ignored.
  void add(const uint8_t* frame) {
    if (count_ >= max_count) return;
    for (size_t i = 0; i < cells; ++i) sum_[i] = static_cast<uint16_t>(sum_[i] + frame[i]);
    ++count_;
  }

  // Write the rounded per-cell mean into out and start a new window. Returns false (out untouched)
  // when no frame arrived in the window.
  bool take_mean(uint8_t* out) {
    if (count_ == 0) return false;
    for (size_t i = 0; i < cells; ++i) {
      out[i] = static_cast<uint8_t>((sum_[i] + count_ / 2) / count_);
      sum_[i] = 0;
    }
    count_ = 0;
    return true;
  }

 private:
  uint16_t sum_[cells] = {};
  uint16_t count_ = 0;
};
