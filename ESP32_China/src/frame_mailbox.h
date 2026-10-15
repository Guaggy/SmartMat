#pragma once

// Hand-off between the USB loop (core 1) and the network task (core 0), plus the MQTT payload formatting.
// Header-only, no Arduino or FreeRTOS includes (so it also builds in the native host test): the caller
// wraps put() and take_if_new() in its own lock.

#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

// Latest-wins mailbox: one averaged frame plus a sequence number. The writer never waits for the reader;
// a frame the reader has not taken yet is simply overwritten by the next one.
struct FrameMailbox {
  static const size_t cells = 400; // 20x20

  uint8_t frame[cells] = {};
  uint32_t seq = 0;   // incremented by every put()
  bool valid = false; // false until the first put()

  void put(const uint8_t* src) {
    memcpy(frame, src, cells);
    ++seq;
    valid = true;
  }

  // Copy the frame into out if it is newer than last_seq (and update last_seq). False = nothing new.
  bool take_if_new(uint32_t& last_seq, uint8_t* out) const {
    if (!valid || seq == last_seq) return false;
    memcpy(out, frame, cells);
    last_seq = seq;
    return true;
  }
};

// 400 comma-separated ints, row-major. out needs cells * 4 bytes ("255," per cell, last comma is the '\0').
inline void format_frame_csv(const uint8_t* frame, size_t cells, char* out) {
  for (size_t i = 0; i < cells; ++i) {
    if (i) *out++ = ',';
    const uint8_t v = frame[i];
    if (v >= 100) *out++ = '0' + v / 100;
    if (v >= 10) *out++ = '0' + (v / 10) % 10;
    *out++ = '0' + v % 10;
  }
  *out = '\0';
}

// Model names go into a CSV field: letters, digits, '_' and '-' only, not empty.
inline bool valid_model(const char* model) {
  if (!model || !*model) return false;
  for (const char* c = model; *c; ++c) {
    if (!isalnum(static_cast<unsigned char>(*c)) && *c != '_' && *c != '-') return false;
  }
  return true;
}

// "<chip_id>,<rows>,<cols>,<value_max>,<model>,<width_mm>,<height_mm>". False on a bad model, a zero size
// or a too small buffer (out is then not a valid meta message).
inline bool format_meta(char* out, size_t out_size, const char* chip_id, unsigned rows, unsigned cols,
                        unsigned value_max, const char* model, unsigned width_mm, unsigned height_mm) {
  if (!valid_model(model) || width_mm == 0 || height_mm == 0) return false;
  const int n = snprintf(out, out_size, "%s,%u,%u,%u,%s,%u,%u", chip_id, rows, cols, value_max, model,
                         width_mm, height_mm);
  return n > 0 && static_cast<size_t>(n) < out_size;
}
