// Mat passport rules, no Arduino and no storage: what the firmware decides about a passport slot.
//
// A passport is the calibration that belongs to this mat, kept on the board so it travels with the mat. Two slots,
// `factory` (needs the service key) and `custom` (anyone with the MQTT login), each an opaque blob of at most
// kMaxBytes that starts with "SMP1" (the Pi side makes it: MAGIC + zlib(JSON), see Raspberry Pi/processing/passport.py).
// The firmware never parses the content; it checks the start bytes and the size, keeps the bytes, and reports their CRC-32.
//
// This header is a twin of Raspberry Pi/passport_device.py (same rules, same message texts); the protocol is in
// PASSPORT.md. Host test: pio test -e native -f test_passport.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace passport {

constexpr size_t kMaxBytes = 16384;
constexpr size_t kSerialMax = 24;
constexpr char kMagic[4] = {'S', 'M', 'P', '1'};

enum class Slot : uint8_t { Invalid, Factory, Custom };

inline Slot parse_slot(const char* name, size_t length) {
  if (length == 7 && memcmp(name, "factory", 7) == 0) return Slot::Factory;
  if (length == 6 && memcmp(name, "custom", 6) == 0) return Slot::Custom;
  return Slot::Invalid;
}

inline const char* slot_name(Slot slot) {
  return slot == Slot::Factory ? "factory" : slot == Slot::Custom ? "custom" : "";
}

// CRC-32 (IEEE, the one zlib.crc32 computes); pass the previous result as `crc` to continue over several chunks
inline uint32_t crc32(const uint8_t* data, size_t length, uint32_t crc = 0) {
  crc = ~crc;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xEDB88320U & (0U - (crc & 1U)));
  }
  return ~crc;
}

enum class Put : uint8_t { Ok, Slot, Empty, TooBig, BadMagic, Locked };

inline const char* put_error(Put result) {
  switch (result) {
    case Put::Slot: return "slot";
    case Put::Empty: return "empty";
    case Put::TooBig: return "too_big";
    case Put::BadMagic: return "bad_magic";
    case Put::Locked: return "locked";
    default: return "";
  }
}

// "KEY:<key>\n<rest>": a payload that carries the service key in front. false when there is no such header.
inline bool split_key(const uint8_t* payload, size_t length, const uint8_t** key, size_t* key_length,
                      const uint8_t** rest, size_t* rest_length) {
  if (length < 5 || memcmp(payload, "KEY:", 4) != 0) return false;
  for (size_t i = 4; i < length; ++i) {
    if (payload[i] == '\n') {
      *key = payload + 4;
      *key_length = i - 4;
      *rest = payload + i + 1;
      *rest_length = length - i - 1;
      return true;
    }
  }
  return false;
}

// Compare without stopping at the first difference; never true for a board that has no service key
inline bool key_matches(const char* expected, const uint8_t* got, size_t got_length) {
  const size_t expected_length = expected == nullptr ? 0 : strlen(expected);
  if (expected_length == 0) return false;
  size_t difference = expected_length ^ got_length;
  const size_t longest = expected_length > got_length ? expected_length : got_length;
  for (size_t i = 0; i < longest; ++i) {
    const uint8_t a = i < expected_length ? static_cast<uint8_t>(expected[i]) : 0;
    const uint8_t b = i < got_length ? got[i] : 0;
    difference |= static_cast<size_t>(a ^ b);
  }
  return difference == 0;
}

// What to do with a payload published to passport/put/<slot>. On Ok, blob/blob_length is what to store (the key line is not).
inline Put check_put(Slot slot, const uint8_t* payload, size_t length, const char* service_key, const uint8_t** blob,
                     size_t* blob_length) {
  if (slot == Slot::Invalid) return Put::Slot;
  *blob = payload;
  *blob_length = length;
  if (slot == Slot::Factory) {
    const uint8_t* key;
    size_t key_length;
    if (!split_key(payload, length, &key, &key_length, blob, blob_length) || !key_matches(service_key, key, key_length)) {
      return Put::Locked;
    }
  }
  if (*blob_length == 0) return Put::Empty;
  if (*blob_length > kMaxBytes) return Put::TooBig;
  if (*blob_length < sizeof(kMagic) || memcmp(*blob, kMagic, sizeof(kMagic)) != 0) return Put::BadMagic;
  return Put::Ok;
}

inline bool valid_serial(const uint8_t* text, size_t length) {
  if (length < 1 || length > kSerialMax) return false;
  for (size_t i = 0; i < length; ++i) {
    const uint8_t c = text[i];
    const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-';
    if (!ok) return false;
  }
  return true;
}

// A name from a topic or payload as it is echoed in a reply: letters, digits, '_' and '-' only, 16 characters at most
inline void safe_name(const char* text, size_t length, char out[17]) {
  size_t used = 0;
  for (size_t i = 0; i < length && used < 16; ++i) {
    const char c = text[i];
    const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-';
    out[used++] = ok ? c : '?';
  }
  out[used] = '\0';
}

struct SlotInfo {
  bool present;
  uint32_t bytes;
  uint32_t crc;
};

inline int format_slot(char* out, size_t capacity, const SlotInfo& info) {
  if (!info.present) return snprintf(out, capacity, "null");
  return snprintf(out, capacity, "{\"bytes\":%lu,\"crc\":\"%08lx\"}", static_cast<unsigned long>(info.bytes),
                  static_cast<unsigned long>(info.crc));
}

// The retained message on passport. Returns its length, or 0 when it does not fit.
inline size_t format_summary(char* out, size_t capacity, const char* serial, const SlotInfo& factory,
                             const SlotInfo& custom) {
  char factory_text[48], custom_text[48];
  format_slot(factory_text, sizeof(factory_text), factory);
  format_slot(custom_text, sizeof(custom_text), custom);
  const int written = snprintf(out, capacity, "{\"serial\":\"%s\",\"factory\":%s,\"custom\":%s,\"max\":%lu}", serial,
                               factory_text, custom_text, static_cast<unsigned long>(kMaxBytes));
  return written > 0 && static_cast<size_t>(written) < capacity ? static_cast<size_t>(written) : 0;
}

// The reply on passport/ack. `slot` must already be safe_name'd. `info` (may be null) adds bytes and crc to an ok reply.
inline size_t format_ack(char* out, size_t capacity, const char* op, const char* slot, bool ok, const char* err,
                         const SlotInfo* info) {
  int written;
  if (!ok) {
    written = snprintf(out, capacity, "{\"op\":\"%s\",\"slot\":\"%s\",\"ok\":false,\"err\":\"%s\"}", op, slot, err);
  } else if (info != nullptr) {
    written = snprintf(out, capacity, "{\"op\":\"%s\",\"slot\":\"%s\",\"ok\":true,\"bytes\":%lu,\"crc\":\"%08lx\"}", op, slot,
                       static_cast<unsigned long>(info->bytes), static_cast<unsigned long>(info->crc));
  } else {
    written = snprintf(out, capacity, "{\"op\":\"%s\",\"slot\":\"%s\",\"ok\":true}", op, slot);
  }
  return written > 0 && static_cast<size_t>(written) < capacity ? static_cast<size_t>(written) : 0;
}

}  // namespace passport
