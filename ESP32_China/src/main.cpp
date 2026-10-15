// SmartMat China mat bridge: ESP32-S3 is a USB host for the Maxrays 20x20 mat (CH340, 921600 baud)
// and republishes its frames over MQTT, same topics as ESP32_Resistive but raw 0-255 values.
// Build with -DSIMULATE_MAT to skip USB and publish a moving blob instead (no mat needed).

#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <cmath>
#include <cstdio>
#include <cstring>

#ifndef SIMULATE_MAT
#include <EspUsbHost.h>
#endif

#include "maxrays_decoder.h"
#include "secrets.h" // Wifi and passcodes

// CONFIG
const bool serial_debug = true; // print debug info to the UART serial port

// Grid and values (raw mat units, scaled to the app's 0-1000 on the Pi using value_max from meta)
const uint8_t grid_rows = 20;
const uint8_t grid_cols = 20;
const uint16_t value_max = 255;
const uint16_t cell_count = grid_rows * grid_cols;

// USB host (native port: D+ GPIO20, D- GPIO19)
const uint32_t mat_baud = 921600; // CH340, 8-N-1
const size_t usb_rx_buffer_size = 8192; // default 512 B is only ~5 ms at 921600

const uint32_t frame_interval_ms = 100; // publish at most 10 fps, latest frame only

// Wifi and MQTT
const char* mqtt_topic_prefix = "smartmat"; // topics: smartmat/<chip_id>/frame and .../meta
const uint32_t reconnect_retry_interval_ms = 5000;
const uint16_t mqtt_socket_timeout_s = 2; // a blocked connect() must not starve the USB ring buffer for 15 s
const uint16_t mqtt_packet_buffer_size = 2048; // 400 values are <= 1.6 KB --> this leaves headroom

// Variables
MaxraysDecoder decoder;
uint8_t latest_frame[cell_count];   // newest decoded (or simulated) frame, raw 0-255
bool frame_is_new = false;          // latest_frame not published yet
char frame_text[cell_count * 4 + 1]; // "255," per cell
char chip_id[13];     // 12 hex digits, also used as MQTT client id (must be unique per board)
char frame_topic[40];
char meta_topic[40];
char meta_text[32];   // "<chip_id>,<rows>,<cols>,<value_max>"

// Start Wifi and MQTT
WiFiClient wifi_client;
PubSubClient mqtt_client(wifi_client);
uint32_t last_wifi_attempt_ms = 0;
uint32_t last_mqtt_attempt_ms = 0;
uint32_t last_frame_sent_ms = 0;

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
  snprintf(meta_text, sizeof(meta_text), "%s,%u,%u,%u", chip_id,
           static_cast<unsigned>(grid_rows), static_cast<unsigned>(grid_cols), static_cast<unsigned>(value_max));
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
  if (mqtt_client.connect(chip_id, mqtt_username, mqtt_password)) {
    mqtt_client.publish(meta_topic, meta_text, true); // retained: a Pi that subscribes later still gets it
    if (serial_debug) Serial.printf("MQTT connected as %s\n", chip_id);
  } else if (serial_debug) {
    Serial.println("MQTT not connected, will try again ...");
  }
}

// Build data frame for MQTT: 400 comma-separated ints, row-major
void build_frame_text() {
  char* out = frame_text;
  for (uint16_t i = 0; i < cell_count; ++i) {
    if (i) *out++ = ',';
    const uint8_t v = latest_frame[i];
    if (v >= 100) *out++ = '0' + v / 100;
    if (v >= 10) *out++ = '0' + (v / 10) % 10;
    *out++ = '0' + v % 10;
  }
  *out = '\0';
}

// Publish the latest frame if there is a new one and the frame interval has passed
void send_frame() {
  if (!frame_is_new || millis() - last_frame_sent_ms < frame_interval_ms) {
    return;
  }
  frame_is_new = false;
  last_frame_sent_ms = millis();
  if (mqtt_client.connected()) {
    build_frame_text();
    mqtt_client.publish(frame_topic, frame_text, true);
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
  for (uint8_t row = 0; row < grid_rows; ++row) {
    for (uint8_t col = 0; col < grid_cols; ++col) {
      const float dx = col - centre_x;
      const float dy = row - centre_y;
      latest_frame[row * grid_cols + col] = static_cast<uint8_t>(255.0f * expf(-(dx * dx + dy * dy) / 18.0f));
    }
  }
  frame_is_new = true;
}
#else
// Pull everything the USB ring buffer holds through the decoder, keep only the newest frame
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
    decoder.feed(chunk, count, [](const uint8_t* payload) {
      memcpy(latest_frame, payload, cell_count);
      frame_is_new = true;
    });
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
  Serial.printf("[%s] %lu B/s, %lu frames/s, discarded %lu B, invalid %lu\n",
#ifdef SIMULATE_MAT
                "sim",
#else
                mat_serial.connected() ? "mat up" : "mat down",
#endif
                static_cast<unsigned long>(decoder.bytes_received - last_bytes),
                static_cast<unsigned long>(decoder.frames_decoded - last_frames),
                static_cast<unsigned long>(decoder.bytes_discarded),
                static_cast<unsigned long>(decoder.invalid_frames));
  last_bytes = decoder.bytes_received;
  last_frames = decoder.frames_decoded;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("Smartmat China mat V1");
  build_identity();
  Serial.printf("Chip id: %s\n", chip_id);

  WiFi.mode(WIFI_STA);
  mqtt_client.setServer(mqtt_broker_ip, mqtt_port);
  mqtt_client.setBufferSize(mqtt_packet_buffer_size);
  mqtt_client.setSocketTimeout(mqtt_socket_timeout_s);

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

  Serial.println("Boot OK");
}

void loop() {
  maintain_wifi();
  maintain_mqtt();

#ifdef SIMULATE_MAT
  simulate_frame();
#else
  read_mat();
#endif
  send_frame();

  if (serial_debug) print_stats();
  delay(1);
}
