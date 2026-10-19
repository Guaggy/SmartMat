// The mat passport on the board (PASSPORT.md): two opaque slots in flash and the MQTT commands that read and write them.
// The decisions (who may write, what is accepted, what is answered) are in mat_passport.h, tested on the PC; this file is
// only the glue to LittleFS and PubSubClient. Same file in ESP32_China and ESP32_Resistive (a test keeps them identical).
//
// Use: begin() once in setup() after LittleFS-capable boot, on_connect() after every MQTT connect, and forward the
// PubSubClient callback to on_message(). Everything runs in the one task that calls mqtt_client.loop().
#pragma once

#include <Arduino.h>
#include <LittleFS.h>
#include <PubSubClient.h>

#include "mat_passport.h"

class PassportService {
 public:
  // client: the MQTT client (its buffer must hold a slot: passport::kMaxBytes + 512). service_key may be "" (read-only factory slot).
  void begin(PubSubClient* client, const char* topic_prefix, const char* chip_id, const char* service_key) {
    client_ = client;
    service_key_ = service_key;
    snprintf(topic_, sizeof(topic_), "%s/%s/passport", topic_prefix, chip_id);
    snprintf(ack_topic_, sizeof(ack_topic_), "%s/ack", topic_);
    snprintf(data_prefix_, sizeof(data_prefix_), "%s/data/", topic_);
    storage_ok_ = LittleFS.begin(true);   // true: format on first use, the slots then simply start empty
    serial_[0] = '\0';
    File file = LittleFS.open("/pp_serial", "r");
    if (file) {
      char text[passport::kSerialMax + 1];
      const size_t count = file.readBytes(text, passport::kSerialMax);
      if (passport::valid_serial(reinterpret_cast<const uint8_t*>(text), count)) {
        memcpy(serial_, text, count);
        serial_[count] = '\0';
      }
      file.close();
    }
    for (int i = 0; i < 2; ++i) info_[i] = read_slot_info(file_of(i));
  }

  bool storage_ok() const { return storage_ok_; }
  const char* serial() const { return serial_; }
  bool has(passport::Slot slot) const { return info_[index(slot)].present; }

  void on_connect() {
    // Explicit topics, not passport/#: the board's own ack and data messages must not come back to it
    char topic[64];
    const char* const commands[] = {"get", "clear", "serial", "put/factory", "put/custom"};
    for (const char* command : commands) {
      snprintf(topic, sizeof(topic), "%s/%s", topic_, command);
      client_->subscribe(topic);
    }
    publish_summary();
  }

  // <prefix>/<chip_id>/passport/get | clear | serial | put/<slot>
  void on_message(const char* topic, const uint8_t* payload, unsigned int length) {
    const char* tail = strstr(topic, "/passport/");
    if (tail == nullptr) return;
    tail += strlen("/passport/");
    if (strcmp(tail, "get") == 0) {
      get(reinterpret_cast<const char*>(payload), length);
    } else if (strcmp(tail, "clear") == 0) {
      clear(payload, length);
    } else if (strcmp(tail, "serial") == 0) {
      set_serial(payload, length);
    } else if (strncmp(tail, "put/", 4) == 0) {
      put(tail + 4, strlen(tail + 4), payload, length);
    }
  }

 private:
  static const char* file_of(int i) { return i == 0 ? "/pp_factory" : "/pp_custom"; }   // a function: no C++17 inline variable needed

  static int index(passport::Slot slot) { return slot == passport::Slot::Factory ? 0 : 1; }

  static passport::SlotInfo read_slot_info(const char* path) {
    passport::SlotInfo info = {false, 0, 0};
    File file = LittleFS.open(path, "r");
    if (!file) return info;
    uint8_t chunk[256];
    uint32_t crc = 0;
    while (file.available()) {
      const size_t count = file.read(chunk, sizeof(chunk));
      if (count == 0) break;
      crc = passport::crc32(chunk, count, crc);
      info.bytes += count;
    }
    file.close();
    info.present = info.bytes > 0;
    info.crc = crc;
    return info;
  }

  // Write to a temporary file and rename, so a power cut leaves the old slot whole
  static bool store_file(const char* path, const uint8_t* data, size_t length) {
    char temp[24];
    snprintf(temp, sizeof(temp), "%s.tmp", path);
    File file = LittleFS.open(temp, "w");
    if (!file) return false;
    const bool wrote = file.write(data, length) == length;
    file.close();
    if (!wrote) {
      LittleFS.remove(temp);
      return false;
    }
    LittleFS.remove(path);
    return LittleFS.rename(temp, path);
  }

  void publish_summary() {
    char text[160];
    if (passport::format_summary(text, sizeof(text), serial_, info_[0], info_[1]) > 0) {
      client_->publish(topic_, text, true);
    }
  }

  void ack(const char* op, const char* slot_text, size_t slot_length, bool ok, const char* err,
           const passport::SlotInfo* info) {
    char slot[17], text[128];
    passport::safe_name(slot_text, slot_length, slot);
    if (passport::format_ack(text, sizeof(text), op, slot, ok, err, info) > 0) {
      client_->publish(ack_topic_, text, false);
    }
  }

  // PubSubClient reuses one buffer for what it receives and what it sends: after the first publish inside a callback the
  // payload is gone, so everything below reads the payload first and publishes last.
  void put(const char* name, size_t name_length, const uint8_t* payload, size_t length) {
    char echo[17];
    passport::safe_name(name, name_length, echo);
    const passport::Slot slot = passport::parse_slot(name, name_length);
    const uint8_t* blob = nullptr;
    size_t blob_length = 0;
    const passport::Put verdict = passport::check_put(slot, payload, length, service_key_, &blob, &blob_length);
    if (verdict != passport::Put::Ok) {
      ack("put", echo, strlen(echo), false, passport::put_error(verdict), nullptr);
      return;
    }
    const int i = index(slot);
    if (!storage_ok_ || !store_file(file_of(i), blob, blob_length)) {
      ack("put", echo, strlen(echo), false, "storage", nullptr);
      return;
    }
    info_[i] = read_slot_info(file_of(i));
    ack("put", echo, strlen(echo), true, nullptr, &info_[i]);
    publish_summary();
  }

  void get(const char* name, size_t name_length) {
    char echo[17];
    passport::safe_name(name, name_length, echo);
    const passport::Slot slot = passport::parse_slot(name, name_length);
    if (slot == passport::Slot::Invalid) {
      ack("get", echo, strlen(echo), false, "slot", nullptr);
      return;
    }
    File file = LittleFS.open(file_of(index(slot)), "r");
    if (!file || file.size() == 0) {
      ack("get", echo, strlen(echo), false, "empty", nullptr);
      return;
    }
    char topic[sizeof(data_prefix_) + 8];
    snprintf(topic, sizeof(topic), "%s%s", data_prefix_, passport::slot_name(slot));
    // The bytes go out in pieces straight from flash (no second 16 KB buffer); not retained: a read is a one-off
    if (!client_->beginPublish(topic, file.size(), false)) {
      ack("get", echo, strlen(echo), false, "storage", nullptr);
      file.close();
      return;
    }
    uint8_t chunk[256];
    while (file.available()) {
      const size_t count = file.read(chunk, sizeof(chunk));
      if (count == 0) break;
      client_->write(chunk, count);
    }
    client_->endPublish();
    file.close();
  }

  void clear(const uint8_t* payload, size_t length) {
    char echo[17];
    passport::safe_name(reinterpret_cast<const char*>(payload), length, echo);
    const passport::Slot slot = passport::parse_slot(reinterpret_cast<const char*>(payload), length);
    if (slot != passport::Slot::Custom) {   // the factory slot is never cleared over MQTT
      ack("clear", echo, strlen(echo), false, slot == passport::Slot::Factory ? "locked" : "slot", nullptr);
      return;
    }
    LittleFS.remove(file_of(1));
    info_[1] = {false, 0, 0};
    ack("clear", echo, strlen(echo), true, nullptr, nullptr);
    publish_summary();
  }

  void set_serial(const uint8_t* payload, size_t length) {
    const uint8_t *key, *serial;
    size_t key_length, serial_length;
    if (!passport::split_key(payload, length, &key, &key_length, &serial, &serial_length) ||
        !passport::key_matches(service_key_, key, key_length)) {
      ack("serial", "", 0, false, "locked", nullptr);
      return;
    }
    if (!passport::valid_serial(serial, serial_length)) {
      ack("serial", "", 0, false, "serial", nullptr);
      return;
    }
    if (!storage_ok_ || !store_file("/pp_serial", serial, serial_length)) {
      ack("serial", "", 0, false, "storage", nullptr);
      return;
    }
    memcpy(serial_, serial, serial_length);
    serial_[serial_length] = '\0';
    ack("serial", "", 0, true, nullptr, nullptr);
    publish_summary();
  }

  PubSubClient* client_ = nullptr;
  const char* service_key_ = "";
  bool storage_ok_ = false;
  char topic_[48], ack_topic_[52], data_prefix_[56];
  char serial_[passport::kSerialMax + 1];
  passport::SlotInfo info_[2] = {{false, 0, 0}, {false, 0, 0}};   // factory, custom
};
