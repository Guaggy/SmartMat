#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <cstdio>

namespace {

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
// This pin map matches the final wiring table. Mux A drives the 16-line
// sensor axis; mux B reads the 15-line axis through GPIO34.

const uint8_t adc_read_pin = 34;

const uint8_t mux_a_enable_pin = 18;
const uint8_t mux_a_select_pins[4] = {19, 21, 22, 23};

const uint8_t mux_b_enable_pin = 27;
const uint8_t mux_b_select_pins[4] = {26, 25, 33, 32};

const uint8_t grid_rows = 16;
const uint8_t grid_cols = 15;

// ---------------------------------------------------------------------------
// Sensor reading & filtering
// ---------------------------------------------------------------------------

const uint8_t samples_per_cell = 4;
const uint16_t address_settling_delay_us = 2;

// Assumes there's no 10 nF capacitor directly on GPIO34. If one is fitted,
// start around 500 us and tune downward while watching for ghosting.
const uint16_t mux_settling_delay_us = 100;
const uint16_t adc_resample_delay_us = 5;

const uint16_t adc_raw_max = 4095;
const uint16_t normalized_max = 1000;

const bool smoothing_enabled = true;
const float smoothing_strength = 0.7f;  // 0 = no smoothing, near 1 = smoother but slower to react

// Serial output is the practical speed limit, but this also caps the
// firmware at ten frames per second.
const uint32_t frame_interval_ms = 100;

// ---------------------------------------------------------------------------
// Wi-Fi & MQTT
// ---------------------------------------------------------------------------
// Wi-Fi and MQTT credentials live in secrets.h, which is gitignored so they
// never get committed. Copy secrets.h.example to secrets.h and fill in your
// own values if you don't already have one.
#include "secrets.h"

const char* mqtt_topic = "smartmat/frame";
const char* mqtt_client_name = "smartmat-esp32";
const uint32_t reconnect_retry_interval_ms = 5000;
const uint16_t mqtt_packet_buffer_size = 1500;  // a 240-value frame is ~1.2 KB; this leaves headroom

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

float filtered_grid[grid_rows][grid_cols] = {};
bool filter_has_started = false;

char frame_text[mqtt_packet_buffer_size - 100];  // grid_rows * grid_cols numbers, comma-separated

WiFiClient wifi_client;
PubSubClient mqtt_client(wifi_client);
uint32_t last_wifi_attempt_ms = 0;
uint32_t last_mqtt_attempt_ms = 0;

void configure_output_pin(uint8_t pin, uint8_t initial_level) {
  // Preload the output latch before enabling the output driver. This keeps
  // the active-low mux enable pins HIGH while the board starts.
  digitalWrite(pin, initial_level);
  pinMode(pin, OUTPUT);
}

void set_mux_enabled(uint8_t enable_pin, bool enabled) {
  digitalWrite(enable_pin, enabled ? LOW : HIGH);
}

void disable_muxes() {
  set_mux_enabled(mux_a_enable_pin, false);
  set_mux_enabled(mux_b_enable_pin, false);
}

void write_mux_address(const uint8_t select_pins[4], uint8_t channel) {
  for (uint8_t bit = 0; bit < 4; ++bit) {
    digitalWrite(select_pins[bit], (channel >> bit) & 0x01U ? HIGH : LOW);
  }
}

void select_cell(uint8_t row, uint8_t col) {
  disable_muxes();
  write_mux_address(mux_a_select_pins, row);
  write_mux_address(mux_b_select_pins, col);
  delayMicroseconds(address_settling_delay_us);

  // Connect the measurement side before connecting the 3.3 V drive side.
  set_mux_enabled(mux_b_enable_pin, true);
  set_mux_enabled(mux_a_enable_pin, true);
  delayMicroseconds(mux_settling_delay_us);
}

uint16_t read_cell(uint8_t row, uint8_t col) {
  select_cell(row, col);

  // Discard the first conversion after changing channels so charge left from
  // the previous cell has less influence on the result.
  (void)analogRead(adc_read_pin);
  delayMicroseconds(adc_resample_delay_us);

  uint32_t raw_sum = 0;
  for (uint8_t sample = 0; sample < samples_per_cell; ++sample) {
    raw_sum += analogRead(adc_read_pin);
    if (sample + 1 < samples_per_cell) {
      delayMicroseconds(adc_resample_delay_us);
    }
  }

  disable_muxes();

  const uint32_t average_raw = (raw_sum + samples_per_cell / 2U) / samples_per_cell;
  return static_cast<uint16_t>((average_raw * normalized_max + adc_raw_max / 2U) / adc_raw_max);
}

void scan_grid() {
  for (uint8_t row = 0; row < grid_rows; ++row) {
    for (uint8_t col = 0; col < grid_cols; ++col) {
      const float measurement = read_cell(row, col);
      if (smoothing_enabled && filter_has_started) {
        filtered_grid[row][col] = smoothing_strength * filtered_grid[row][col] +
                                   (1.0f - smoothing_strength) * measurement;
      } else {
        filtered_grid[row][col] = measurement;
      }
    }
  }

  filter_has_started = true;
  disable_muxes();
}

// Renders the current grid as one comma-separated line of integers, e.g.
// "12,340,0,...". Shared by the serial print and the MQTT payload so the
// two outputs can never drift apart.
void build_frame_text() {
  size_t offset = 0;
  for (uint8_t row = 0; row < grid_rows; ++row) {
    for (uint8_t col = 0; col < grid_cols; ++col) {
      if (offset > 0) {
        frame_text[offset++] = ',';
      }
      const int value = static_cast<int>(filtered_grid[row][col] + 0.5f);
      offset += snprintf(frame_text + offset, sizeof(frame_text) - offset, "%d", value);
    }
  }
  frame_text[offset] = '\0';
}

bool wifi_is_connected() {
  return WiFi.status() == WL_CONNECTED;
}

// Kicks off a Wi-Fi connection attempt if we're not already connected.
// Non-blocking: WiFi.begin() returns immediately and the connection finishes
// in the background over the following loop() iterations, so the mat keeps
// scanning and printing over serial the whole time.
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
}

// Reconnects to the broker if needed. mqtt_client.connect() briefly blocks
// while it opens the socket, but that only happens while disconnected (at
// most once every reconnect_retry_interval_ms), never during a normal
// scan/publish cycle.
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
  mqtt_client.connect(mqtt_client_name, mqtt_username, mqtt_password);
}

void send_frame() {
  build_frame_text();
  Serial.println(frame_text);

  if (mqtt_client.connected()) {
    // Retained so a subscriber that connects late still sees the latest
    // frame right away instead of waiting for the next scan.
    mqtt_client.publish(mqtt_topic, frame_text, true);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);

  configure_output_pin(mux_a_enable_pin, HIGH);
  configure_output_pin(mux_b_enable_pin, HIGH);

  for (uint8_t bit = 0; bit < 4; ++bit) {
    configure_output_pin(mux_a_select_pins[bit], LOW);
    configure_output_pin(mux_b_select_pins[bit], LOW);
  }

  pinMode(adc_read_pin, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(adc_read_pin, ADC_11db);

  WiFi.mode(WIFI_STA);
  mqtt_client.setServer(mqtt_broker_ip, mqtt_port);
  mqtt_client.setBufferSize(mqtt_packet_buffer_size);

  delay(200);
  Serial.println("# Boot OK: SmartMat 16x15");
}

void loop() {
  const uint32_t frame_started_ms = millis();

  maintain_wifi();
  maintain_mqtt();

  scan_grid();
  send_frame();

  const uint32_t elapsed_ms = millis() - frame_started_ms;
  if (elapsed_ms < frame_interval_ms) {
    delay(frame_interval_ms - elapsed_ms);
  }
}
