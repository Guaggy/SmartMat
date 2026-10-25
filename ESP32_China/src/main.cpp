// SmartMat China mat bridge: ESP32-S3 is a USB host for the Maxrays 20x20 mat (CH340, 921600 baud)
// and republishes its frames over MQTT, same topics as ESP32_Resistive but raw 0-255 values.
// Build with -DSIMULATE_MAT to skip USB and publish a moving blob instead (no mat needed).
//
// Two cores: the Arduino loop (core 1) only drains USB, decodes and averages, and never blocks. All Wi-Fi and
// MQTT work runs in network_task (core 0, next to the Wi-Fi/lwIP tasks), because a broker or Wi-Fi outage
// blocks connect() for seconds and the 8 KB USB buffer holds only ~0.3 s of the mat's ~24 kB/s stream.
// The two meet in one latest-wins mailbox (frame_mailbox.h), filled once per 100 ms window.

#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <cmath>
#include <cstdio>
#include <cstring>

#ifndef SIMULATE_MAT
#include <EspUsbHost.h>
#endif

#include "frame_accumulator.h"
#include "frame_mailbox.h"
#include "maxrays_decoder.h"
#include "passport_service.h"
#include "secrets.h" // Wifi and passcodes

// CONFIG
const bool serial_debug = true; // print debug info to the UART serial port

// Grid and values (raw mat units, scaled to the app's 0-1000 on the Pi using value_max from meta)
const uint8_t grid_rows = 20;
const uint8_t grid_cols = 20;
const uint16_t value_max = 255;
const uint16_t cell_count = grid_rows * grid_cols;

// Mat preset, sent in the meta message. Sensing area measured from the MC266 datasheet drawing,
// approximate (+/-5 %): verify with a ruler. Model: letters, digits, '_' and '-' only; sizes in whole mm.
const char* MAT_MODEL = "MC266";
const uint16_t MAT_WIDTH_MM = 343;
const uint16_t MAT_HEIGHT_MM = 358;

// USB host (native port: D+ GPIO20, D- GPIO19)
const uint32_t mat_baud = 921600; // CH340, 8-N-1
const size_t usb_rx_buffer_size = 8192; // default 512 B is only ~5 ms at 921600

const uint32_t frame_interval_ms = 100; // publish window: 10 fps, mean of all frames decoded in it

// Wifi and MQTT
const char* mqtt_topic_prefix = "smartmat"; // topics: smartmat/<chip_id>/frame, .../meta and .../status
const uint32_t reconnect_retry_interval_ms = 5000;
const uint16_t mqtt_socket_timeout_s = 2; // keeps the network task responsive while the broker is down
// Big enough for a whole passport slot (+ the service key line and the topic): passport.md. Frames are <= 1.6 KB.
const uint16_t mqtt_packet_buffer_size = passport::kMaxBytes + 512;

// Network task: core 0 (the Arduino loop runs on core 1), below the Wi-Fi (23) and lwIP (18) priorities
const BaseType_t network_core = 0;
const UBaseType_t network_priority = 1;
const uint32_t network_stack_bytes = 12288; // free stack is printed in the 1 Hz stats
const uint32_t network_poll_ms = 10;

// Variables (main loop only)
MaxraysDecoder decoder;
FrameAccumulator accumulator; // frames decoded (or simulated) in the current publish window
uint32_t window_start_ms = 0;

// Set in setup(), read-only afterwards
char chip_id[13];     // 12 hex digits, also used as MQTT client id (must be unique per board)
char frame_topic[40];
char meta_topic[40];
char status_topic[40]; // "online" retained after connect, "offline" retained as last will
char meta_text[64];   // "<chip_id>,<rows>,<cols>,<value_max>,<model>,<width_mm>,<height_mm>"

// Shared between the two cores
FrameMailbox mailbox; // guarded by mailbox_lock
portMUX_TYPE mailbox_lock = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t windows_dropped = 0; // written by the network task only
volatile bool mqtt_up = false;         // written by the network task only
TaskHandle_t network_task_handle = nullptr;

// Network task only: never touch these from loop()
WiFiClient wifi_client;
PubSubClient mqtt_client(wifi_client);
PassportService passport_service; // the mat's calibration kept in flash, answered over MQTT (PASSPORT.md)
uint32_t last_wifi_attempt_ms = 0;
uint32_t last_mqtt_attempt_ms = 0;
uint8_t net_frame[cell_count];
char frame_text[cell_count * 4]; // "255," per cell, the last comma's place holds the '\0'

#ifndef SIMULATE_MAT
EspUsbHost usb;
EspUsbHostCdcSerial mat_serial(usb);
bool mat_was_connected = false;
#endif

// Chip id --> MQTT client id, topics and the meta message that tells the Pi our grid size and range
void build_identity() {
  const uint64_t mac = ESP.getEfuseMac();
  snprintf(chip_id, sizeof(chip_id), "%04x%08x",
           static_cast<unsigned>(mac >> 32) & 0xFFFFU, static_cast<unsigned>(mac & 0xFFFFFFFFU));
  snprintf(frame_topic, sizeof(frame_topic), "%s/%s/frame", mqtt_topic_prefix, chip_id);
  snprintf(meta_topic, sizeof(meta_topic), "%s/%s/meta", mqtt_topic_prefix, chip_id);
  snprintf(status_topic, sizeof(status_topic), "%s/%s/status", mqtt_topic_prefix, chip_id);
  if (!format_meta(meta_text, sizeof(meta_text), chip_id, grid_rows, grid_cols, value_max, MAT_MODEL,
                   MAT_WIDTH_MM, MAT_HEIGHT_MM)) {
    for (;;) { // config error in the constants above: fail loudly instead of sending a broken meta
      Serial.println("Bad MAT_MODEL / MAT_WIDTH_MM / MAT_HEIGHT_MM, fix the config and reflash");
      delay(2000);
    }
  }
}


// Check if wifi is connected
bool wifi_is_connected() {
  return WiFi.status() == WL_CONNECTED;
}

// Try to reconnect if no wifi
void maintain_wifi() {
  if (wifi_is_connected()) {
    return;
  }
  const uint32_t now = millis();
  if (now - last_wifi_attempt_ms < reconnect_retry_interval_ms) {
    return;
  }
  last_wifi_attempt_ms = now;
  WiFi.begin(wifi_ssid, wifi_password);
  if (serial_debug) Serial.println("Wifi not connected, will try again ...");
}

// Try to reconnect if no MQTT and run MQTT loop
void maintain_mqtt() {
  if (!wifi_is_connected()) {
    return;
  }
  if (mqtt_client.connected()) {
    mqtt_client.loop();
    return;
  }
  const uint32_t now = millis();
  if (now - last_mqtt_attempt_ms < reconnect_retry_interval_ms) {
    return;
  }
  last_mqtt_attempt_ms = now;
  // Last will: the broker publishes "offline" (retained) on status if we vanish without a clean disconnect
  if (mqtt_client.connect(chip_id, mqtt_username, mqtt_password, status_topic, 0, true, "offline")) {
    mqtt_client.publish(status_topic, "online", true);
    mqtt_client.publish(meta_topic, meta_text, true); // retained: a Pi that subscribes later still gets it
    passport_service.on_connect();
    if (serial_debug) Serial.printf("MQTT connected as %s\n", chip_id);
  } else if (serial_debug) {
    Serial.println("MQTT not connected, will try again ...");
  }
}

// Publish each new window once; a window that arrives while MQTT is down is dropped (and counted)
void publish_frame() {
  static uint32_t last_seq = 0;
  portENTER_CRITICAL(&mailbox_lock);
  const bool fresh = mailbox.take_if_new(last_seq, net_frame);
  portEXIT_CRITICAL(&mailbox_lock);
  if (!fresh) {
    return;
  }
  format_frame_csv(net_frame, cell_count, frame_text);
  // Not retained: a stale frame must not look live
  if (!mqtt_client.connected() || !mqtt_client.publish(frame_topic, frame_text, false)) {
    windows_dropped = windows_dropped + 1;
  }
}

// Owns Wi-Fi and MQTT. connect() may block for seconds here; the USB loop on the other core keeps running.
void network_task(void*) {
  WiFi.mode(WIFI_STA);
  mqtt_client.setServer(mqtt_broker_ip, mqtt_port);
  mqtt_client.setBufferSize(mqtt_packet_buffer_size);
  mqtt_client.setSocketTimeout(mqtt_socket_timeout_s);
  mqtt_client.setCallback([](char* topic, uint8_t* payload, unsigned int length) {
    passport_service.on_message(topic, payload, length);
  });
  for (;;) {
    maintain_wifi();
    maintain_mqtt();
    mqtt_up = mqtt_client.connected();
    publish_frame();
    vTaskDelay(pdMS_TO_TICKS(network_poll_ms));
  }
}

// At the end of each window hand the mean of its frames to the network task (nothing if none arrived)
void close_window() {
  if (millis() - window_start_ms < frame_interval_ms) {
    return;
  }
  window_start_ms = millis();
  uint8_t mean[cell_count];
  if (accumulator.take_mean(mean)) {
    portENTER_CRITICAL(&mailbox_lock); // 400 B memcpy: microseconds, never waits on the network
    mailbox.put(mean);
    portEXIT_CRITICAL(&mailbox_lock);
  }
}

#ifdef SIMULATE_MAT
// Gaussian blob on a Lissajous path, 0-255, new frame every frame_interval_ms
void simulate_frame() {
  static uint32_t last_sim_ms = 0;
  const uint32_t now = millis();
  if (now - last_sim_ms < frame_interval_ms) {
    return;
  }
  last_sim_ms = now;

  const float t = now / 1000.0f;
  const float centre_x = (grid_cols - 1) / 2.0f + 6.0f * sinf(t * 0.9f);
  const float centre_y = (grid_rows - 1) / 2.0f + 6.0f * cosf(t * 0.6f);
  uint8_t frame[cell_count];
  for (uint8_t row = 0; row < grid_rows; ++row) {
    for (uint8_t col = 0; col < grid_cols; ++col) {
      const float dx = col - centre_x;
      const float dy = row - centre_y;
      frame[row * grid_cols + col] = static_cast<uint8_t>(255.0f * expf(-(dx * dx + dy * dy) / 18.0f));
    }
  }
  accumulator.add(frame);
}
#else
// Pull everything the USB ring buffer holds through the decoder, adding each frame to the window average
void read_mat() {
  const bool connected = mat_serial.connected();
  if (connected != mat_was_connected) {
    mat_was_connected = connected;
    decoder.reset(); // never join half a packet from before the unplug with the new stream
    if (serial_debug) Serial.println(connected ? "Mat connected" : "Mat disconnected");
  }

  uint8_t chunk[256];
  while (mat_serial.available() > 0) {
    size_t count = 0;
    while (count < sizeof(chunk) && mat_serial.available() > 0) {
      chunk[count++] = static_cast<uint8_t>(mat_serial.read());
    }
#ifdef DUMP_RAW  // diagnostic: print the first ~900 raw bytes of the mat stream as hex, once
    static size_t dumped = 0;
    if (dumped < 900) {
      if (dumped == 0) Serial.println("\n--- raw dump start ---");
      for (size_t i = 0; i < count; ++i) Serial.printf("%02X ", chunk[i]);
      dumped += count;
      if (dumped >= 900) Serial.println("\n--- raw dump end ---");
    }
#endif
    decoder.feed(chunk, count, [](const uint8_t* payload) { accumulator.add(payload); });
  }
}
#endif

// Print mat statistics once a second
void print_stats() {
  static uint32_t last_print_ms = 0;
  static uint32_t last_bytes = 0;
  static uint32_t last_frames = 0;
  const uint32_t now = millis();
  if (now - last_print_ms < 1000) {
    return;
  }
  last_print_ms = now;
  Serial.printf("[%s, %s] %lu B/s, %lu frames/s, discarded %lu B, invalid %lu, net dropped %lu, "
                "net stack free %u B\n",
#ifdef SIMULATE_MAT
                "sim",
#else
                mat_serial.connected() ? "mat up" : "mat down",
#endif
                mqtt_up ? "mqtt up" : "mqtt down",
                static_cast<unsigned long>(decoder.bytes_received - last_bytes),
                static_cast<unsigned long>(decoder.frames_decoded - last_frames),
                static_cast<unsigned long>(decoder.bytes_discarded),
                static_cast<unsigned long>(decoder.invalid_frames),
                static_cast<unsigned long>(windows_dropped),
                static_cast<unsigned>(uxTaskGetStackHighWaterMark(network_task_handle)));
  last_bytes = decoder.bytes_received;
  last_frames = decoder.frames_decoded;
}

void setup() {
  Serial.setTxBufferSize(1024); // default 0 = printf() blocks the USB loop until the line is on the wire
  Serial.begin(115200);
  delay(500);
  Serial.println("Smartmat China mat V1");
  build_identity();
  Serial.printf("Chip id: %s\n", chip_id);
  passport_service.begin(&mqtt_client, mqtt_topic_prefix, chip_id, passport_service_key);
  Serial.printf("Passport: serial '%s', factory %s, custom %s%s\n", passport_service.serial(),
                passport_service.has(passport::Slot::Factory) ? "yes" : "no",
                passport_service.has(passport::Slot::Custom) ? "yes" : "no",
                passport_service.storage_ok() ? "" : " (flash storage failed)");

#ifdef SIMULATE_MAT
  Serial.println("SIMULATE_MAT: USB host off, publishing a moving blob");
#else
  // The library rebinds the port on replug, so reconnect needs no extra code.
  mat_serial.setRxBufferSize(usb_rx_buffer_size);
  mat_serial.begin(mat_baud);
  if (!usb.begin()) {
    Serial.printf("usb.begin() failed: %s\n", usb.lastErrorName());
  }
#endif

  xTaskCreatePinnedToCore(network_task, "network", network_stack_bytes, nullptr, network_priority,
                          &network_task_handle, network_core);
  Serial.println("Boot OK");
}

// USB loop: no network calls, nothing that blocks
void loop() {
#ifdef SIMULATE_MAT
  simulate_frame();
#else
  read_mat();
#endif
  close_window();

  if (serial_debug) print_stats();
  delay(1);
}
