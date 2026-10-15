#pragma once

// Maxrays 20x20 stream decoder: A5 5A + 2-byte big-endian length + 400 payload bytes + 2 trailer bytes.
// Header-only, no Arduino includes (so it also builds in the native host test).
// Same framing rules as Raspberry Pi/sources/maxrays.py - keep the two in step.
// The 2 trailer bytes are ignored: their checksum is undocumented.

#include <cstddef>
#include <cstdint>
#include <cstring>

class MaxraysDecoder {
 public:
  static const size_t rows = 20;
  static const size_t cols = 20;
  static const size_t cells = rows * cols;
  static const size_t min_size = 4 + cells;    // header + length + payload
  static const size_t max_size = min_size + 32;

  uint32_t bytes_received = 0;
  uint32_t frames_decoded = 0;
  uint32_t bytes_discarded = 0;
  uint32_t invalid_frames = 0;

  // Drop buffered bytes (e.g. when the mat is unplugged); the counters are kept.
  void reset() { used_ = 0; }

  // Feed one serial chunk; on_frame(const uint8_t* payload) is called with the 400 raw
  // values (row-major, 0-255) for every complete frame. The pointer is only valid in the call.
  template <typename OnFrame>
  void feed(const uint8_t* data, size_t len, OnFrame on_frame) {
    bytes_received += static_cast<uint32_t>(len);
    while (len > 0) {
      // drain() always leaves < max_size bytes, so there is always room for at least 1 byte
      size_t take = capacity - used_;
      if (take > len) take = len;
      memcpy(buf_ + used_, data, take);
      used_ += take;
      data += take;
      len -= take;
      drain(on_frame);
    }
  }

 private:
  static const size_t capacity = 2 * max_size;
  uint8_t buf_[capacity];
  size_t used_ = 0;

  // Index of the next A5 5A at or after `from`, or used_ when there is none.
  size_t find_header(size_t from) const {
    for (size_t i = from; i + 1 < used_; ++i) {
      if (buf_[i] == 0xA5 && buf_[i + 1] == 0x5A) return i;
    }
    return used_;
  }

  void erase(size_t count) {
    memmove(buf_, buf_ + count, used_ - count);
    used_ -= count;
    bytes_discarded += static_cast<uint32_t>(count);
  }

  template <typename OnFrame>
  void drain(OnFrame on_frame) {
    while (true) {
      const size_t start = find_header(0);
      if (start == used_) {
        // a trailing lone A5 may be half of the next header
        erase(used_ - ((used_ > 0 && buf_[used_ - 1] == 0xA5) ? 1 : 0));
        return;
      }
      if (start) erase(start);
      if (used_ < min_size) return;

      const size_t declared = (static_cast<size_t>(buf_[2]) << 8) | buf_[3];
      size_t size = 0;  // 0 = no usable declared length
      if (declared >= min_size && declared <= max_size) size = declared;
      else if (declared + 4 >= min_size && declared + 4 <= max_size) size = declared + 4;

      // a header right where the declared length ends confirms the packet (a trailer that
      // happens to read A5 5A cannot fool this); else fall back to header-to-header spacing
      const bool confirmed = size != 0 && size + 2 <= used_ && buf_[size] == 0xA5 && buf_[size + 1] == 0x5A;
      if (!confirmed) {
        const size_t next = find_header(min_size);
        if (next < used_ && next <= max_size) {
          size = next;
        } else if (size != 0 && used_ >= size + 2) {
          size = 0;  // nothing confirms it: a packet that lost bytes
        }
        if (size == 0) {  // false header or truncated packet
          erase(1);
          ++invalid_frames;
          continue;
        }
        if (used_ < size) return;  // wait for the rest of the packet
      }
      on_frame(buf_ + 4);
      ++frames_decoded;
      memmove(buf_, buf_ + size, used_ - size);
      used_ -= size;
    }
  }
};
