// Host test of the passport rules (src/mat_passport.h). The expected texts are the ones
// Raspberry Pi/passport_device.py produces (tests/test_passport.py checks the same strings there).
#include <unity.h>

#include <cstring>

#include "mat_passport.h"

using passport::Put;
using passport::Slot;
using passport::SlotInfo;

static const char* KEY = "s3rv1ce-key";
// MAGIC + a minimal zlib stream: 12 bytes, CRC-32 0bfc9cf7
static const uint8_t BLOB[12] = {'S', 'M', 'P', '1', 0x78, 0x9c, 0x03, 0x00, 0x00, 0x00, 0x00, 0x01};

static const uint8_t* bytes(const char* text) { return reinterpret_cast<const uint8_t*>(text); }

void setUp() {}
void tearDown() {}

void test_crc_standard_check_value() {
  TEST_ASSERT_EQUAL(0xCBF43926U, passport::crc32(bytes("123456789"), 9));
  TEST_ASSERT_EQUAL(0U, passport::crc32(bytes(""), 0));
  TEST_ASSERT_EQUAL(0x0BFC9CF7U, passport::crc32(BLOB, sizeof(BLOB)));
}

void test_crc_over_chunks_equals_crc_in_one_go() {
  const uint32_t first = passport::crc32(bytes("12345"), 5);
  TEST_ASSERT_EQUAL(0xCBF43926U, passport::crc32(bytes("6789"), 4, first));
}

void test_parse_slot() {
  TEST_ASSERT_TRUE(passport::parse_slot("factory", 7) == Slot::Factory);
  TEST_ASSERT_TRUE(passport::parse_slot("custom", 6) == Slot::Custom);
  TEST_ASSERT_TRUE(passport::parse_slot("custom", 5) == Slot::Invalid);
  TEST_ASSERT_TRUE(passport::parse_slot("customs", 7) == Slot::Invalid);
  TEST_ASSERT_TRUE(passport::parse_slot("", 0) == Slot::Invalid);
  TEST_ASSERT_EQUAL_STRING("factory", passport::slot_name(Slot::Factory));
}

void test_custom_slot_takes_a_blob_and_refuses_the_rest() {
  const uint8_t* blob = nullptr;
  size_t length = 0;
  TEST_ASSERT_TRUE(passport::check_put(Slot::Custom, BLOB, sizeof(BLOB), KEY, &blob, &length) == Put::Ok);
  TEST_ASSERT_TRUE(blob == BLOB);
  TEST_ASSERT_EQUAL(12, length);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Custom, BLOB, 0, KEY, &blob, &length) == Put::Empty);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Custom, bytes("XXXXabc"), 7, KEY, &blob, &length) == Put::BadMagic);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Custom, bytes("SMP"), 3, KEY, &blob, &length) == Put::BadMagic);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Invalid, BLOB, sizeof(BLOB), KEY, &blob, &length) == Put::Slot);
  static uint8_t big[passport::kMaxBytes + 1];
  memcpy(big, passport::kMagic, 4);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Custom, big, sizeof(big), KEY, &blob, &length) == Put::TooBig);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Custom, big, passport::kMaxBytes, KEY, &blob, &length) == Put::Ok);  // exactly the limit
}

void test_factory_slot_needs_the_service_key() {
  uint8_t payload[64];
  const uint8_t* blob = nullptr;
  size_t length = 0;
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, BLOB, sizeof(BLOB), KEY, &blob, &length) == Put::Locked);   // no header
  const char* wrong = "KEY:wrong\n";
  memcpy(payload, wrong, strlen(wrong));
  memcpy(payload + strlen(wrong), BLOB, sizeof(BLOB));
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, payload, strlen(wrong) + sizeof(BLOB), KEY, &blob, &length) == Put::Locked);
  const char* longer = "KEY:s3rv1ce-keyx\n";
  memcpy(payload, longer, strlen(longer));
  memcpy(payload + strlen(longer), BLOB, sizeof(BLOB));
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, payload, strlen(longer) + sizeof(BLOB), KEY, &blob, &length) == Put::Locked);
  const char* nonewline = "KEY:s3rv1ce-key";
  memcpy(payload, nonewline, strlen(nonewline));
  memcpy(payload + strlen(nonewline), BLOB, sizeof(BLOB));
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, payload, strlen(nonewline) + sizeof(BLOB), KEY, &blob, &length) == Put::Locked);

  const char* right = "KEY:s3rv1ce-key\n";
  memcpy(payload, right, strlen(right));
  memcpy(payload + strlen(right), BLOB, sizeof(BLOB));
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, payload, strlen(right) + sizeof(BLOB), KEY, &blob, &length) == Put::Ok);
  TEST_ASSERT_EQUAL(12, length);                                // the key line is not part of what is stored
  TEST_ASSERT_EQUAL('S', blob[0]);
  TEST_ASSERT_TRUE(blob == payload + strlen(right));
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, bytes("KEY:s3rv1ce-key\n"), 16, KEY, &blob, &length) == Put::Empty);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, bytes("KEY:s3rv1ce-key\nnope"), 20, KEY, &blob, &length) == Put::BadMagic);
}

void test_a_board_without_a_service_key_has_no_writable_factory_slot() {
  const uint8_t* blob = nullptr;
  size_t length = 0;
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, bytes("KEY:\nSMP1abc"), 12, "", &blob, &length) == Put::Locked);
  TEST_ASSERT_TRUE(passport::check_put(Slot::Factory, bytes("KEY:\nSMP1abc"), 12, nullptr, &blob, &length) == Put::Locked);
  TEST_ASSERT_FALSE(passport::key_matches("", bytes(""), 0));
}

void test_split_key() {
  const uint8_t *key, *rest;
  size_t key_length, rest_length;
  TEST_ASSERT_TRUE(passport::split_key(bytes("KEY:abc\nrest\nmore"), 17, &key, &key_length, &rest, &rest_length));
  TEST_ASSERT_EQUAL(3, key_length);
  TEST_ASSERT_EQUAL(9, rest_length);
  TEST_ASSERT_TRUE(passport::split_key(bytes("KEY:\nx"), 6, &key, &key_length, &rest, &rest_length));
  TEST_ASSERT_EQUAL(0, key_length);
  TEST_ASSERT_FALSE(passport::split_key(bytes("KEY:abc"), 7, &key, &key_length, &rest, &rest_length));
  TEST_ASSERT_FALSE(passport::split_key(bytes("key:abc\nx"), 9, &key, &key_length, &rest, &rest_length));
  TEST_ASSERT_FALSE(passport::split_key(bytes("abc"), 3, &key, &key_length, &rest, &rest_length));
  TEST_ASSERT_FALSE(passport::split_key(bytes(""), 0, &key, &key_length, &rest, &rest_length));
}

void test_serial() {
  TEST_ASSERT_TRUE(passport::valid_serial(bytes("SM-0042"), 7));
  TEST_ASSERT_TRUE(passport::valid_serial(bytes("a_b-C9"), 6));
  TEST_ASSERT_FALSE(passport::valid_serial(bytes(""), 0));
  TEST_ASSERT_FALSE(passport::valid_serial(bytes("has space"), 9));
  TEST_ASSERT_FALSE(passport::valid_serial(bytes("quo\"te"), 6));
  TEST_ASSERT_FALSE(passport::valid_serial(bytes("1234567890123456789012345"), 25));
  TEST_ASSERT_TRUE(passport::valid_serial(bytes("123456789012345678901234"), 24));
}

void test_safe_name_cannot_break_json() {
  char out[17];
  passport::safe_name("custom", 6, out);
  TEST_ASSERT_EQUAL_STRING("custom", out);
  passport::safe_name("a\"b\\c d/e", 9, out);
  TEST_ASSERT_EQUAL_STRING("a?b?c?d?e", out);
  passport::safe_name("0123456789abcdefXYZ", 19, out);
  TEST_ASSERT_EQUAL_STRING("0123456789abcdef", out);
}

void test_summary_texts() {
  char text[160];
  SlotInfo none = {false, 0, 0};
  size_t length = passport::format_summary(text, sizeof(text), "SM-0001", none, none);
  TEST_ASSERT_EQUAL_STRING("{\"serial\":\"SM-0001\",\"factory\":null,\"custom\":null,\"max\":16384}", text);
  TEST_ASSERT_EQUAL(strlen(text), length);
  SlotInfo custom = {true, 12, 0x0BFC9CF7U};
  passport::format_summary(text, sizeof(text), "SM-0001", none, custom);
  TEST_ASSERT_EQUAL_STRING("{\"serial\":\"SM-0001\",\"factory\":null,\"custom\":{\"bytes\":12,\"crc\":\"0bfc9cf7\"},\"max\":16384}", text);
  SlotInfo factory = {true, 3901, 0x000000AAU};
  passport::format_summary(text, sizeof(text), "", factory, custom);
  TEST_ASSERT_EQUAL_STRING("{\"serial\":\"\",\"factory\":{\"bytes\":3901,\"crc\":\"000000aa\"},\"custom\":{\"bytes\":12,\"crc\":\"0bfc9cf7\"},\"max\":16384}", text);
}

void test_a_summary_that_does_not_fit_is_reported_not_cut() {
  char text[20];
  SlotInfo none = {false, 0, 0};
  TEST_ASSERT_EQUAL(0, passport::format_summary(text, sizeof(text), "SM-0001", none, none));
}

void test_ack_texts() {
  char text[128];
  SlotInfo info = {true, 12, 0x0BFC9CF7U};
  passport::format_ack(text, sizeof(text), "put", "custom", true, nullptr, &info);
  TEST_ASSERT_EQUAL_STRING("{\"op\":\"put\",\"slot\":\"custom\",\"ok\":true,\"bytes\":12,\"crc\":\"0bfc9cf7\"}", text);
  passport::format_ack(text, sizeof(text), "put", "factory", false, passport::put_error(Put::Locked), nullptr);
  TEST_ASSERT_EQUAL_STRING("{\"op\":\"put\",\"slot\":\"factory\",\"ok\":false,\"err\":\"locked\"}", text);
  passport::format_ack(text, sizeof(text), "clear", "custom", true, nullptr, nullptr);
  TEST_ASSERT_EQUAL_STRING("{\"op\":\"clear\",\"slot\":\"custom\",\"ok\":true}", text);
  passport::format_ack(text, sizeof(text), "get", "custom", false, passport::put_error(Put::Empty), nullptr);
  TEST_ASSERT_EQUAL_STRING("{\"op\":\"get\",\"slot\":\"custom\",\"ok\":false,\"err\":\"empty\"}", text);
  TEST_ASSERT_EQUAL_STRING("too_big", passport::put_error(Put::TooBig));
  TEST_ASSERT_EQUAL_STRING("bad_magic", passport::put_error(Put::BadMagic));
  TEST_ASSERT_EQUAL_STRING("slot", passport::put_error(Put::Slot));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_crc_standard_check_value);
  RUN_TEST(test_crc_over_chunks_equals_crc_in_one_go);
  RUN_TEST(test_parse_slot);
  RUN_TEST(test_custom_slot_takes_a_blob_and_refuses_the_rest);
  RUN_TEST(test_factory_slot_needs_the_service_key);
  RUN_TEST(test_a_board_without_a_service_key_has_no_writable_factory_slot);
  RUN_TEST(test_split_key);
  RUN_TEST(test_serial);
  RUN_TEST(test_safe_name_cannot_break_json);
  RUN_TEST(test_summary_texts);
  RUN_TEST(test_a_summary_that_does_not_fit_is_reported_not_cut);
  RUN_TEST(test_ack_texts);
  return UNITY_END();
}
