#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <cstdio>
#include <cstring>

#include "secrets.h" // Wifi and passcodes

// CONFIG
const bool serial_debug = true; // print debug info to serial
const bool smoothing_enabled = true; // Enable lowpass filter
const bool send_frame_serial = false; // Send frame over serial
const bool read_linear_voltage = true; // Convert ADC to linear measurements --> can calculate absolute pressure etc.

// Wiring
const uint8_t adc_read_pin = 34;

const uint8_t mux_a_enable_pin = 18;
const uint8_t mux_a_select_pins[4] = {19, 21, 22, 23};
const uint8_t mux_b_enable_pin = 27;
const uint8_t mux_b_select_pins[4] = {26, 25, 33, 32};

const uint8_t grid_rows = 16; // Gnd 
const uint8_t grid_cols = 15; // Adc read pin

// sampling and filtering 
const uint8_t samples_per_cell = 5; 
const uint16_t address_settling_delay_us = 2; // Delay after changing mux channel

const uint16_t mux_settling_delay_us = 100; // Delay after enabling mux
const uint16_t adc_resample_delay_us = 5; // Delay between repeted measurments

const float adc_volt_max = 3.3;
const uint16_t adc_linear_max = static_cast<uint16_t>(adc_volt_max * 1000); // analogReadMilliVolts() max, in mV
const uint16_t adc_raw_max = 4095;
const uint16_t normalized_max = 1000; // Final pressure values = 0-1000

const float smoothing_strength = 0.7f;  // 0 = no smoothing, near 1 = smoother but slower to react

const uint32_t frame_interval_ms = 100; // 10 fps

// Wifi and MQTT
const char* mqtt_topic = "smartmat/frame";
const char* mqtt_client_name = "smartmat-esp32";
const uint32_t reconnect_retry_interval_ms = 5000;
const uint16_t mqtt_packet_buffer_size = 1500;  // 240-value frame is ~1.2 KB --> this leaves headroom

// Variables
float filtered_grid[grid_rows][grid_cols] = {};
bool filter_has_started = false; // Dont apply filter on first full scan
char frame_text[mqtt_packet_buffer_size - 100];  // reserve space for text to send over MQTT/Serial

// Start Wifi and MQTT
WiFiClient wifi_client;
PubSubClient mqtt_client(wifi_client);
uint32_t last_wifi_attempt_ms = 0;
uint32_t last_mqtt_attempt_ms = 0;

// Safer method to initialize mux pins (ex: start with enable pin == HIGH)
void configure_output_pin(uint8_t pin, uint8_t initial_level) {
  digitalWrite(pin, initial_level);
  pinMode(pin, OUTPUT);
}

// Enable/disable invidiual mux
void set_mux_enabled(uint8_t enable_pin, bool enabled) {
  digitalWrite(enable_pin, enabled ? LOW : HIGH);
}

// Disable all muxes
void disable_muxes() {
  set_mux_enabled(mux_a_enable_pin, false);
  set_mux_enabled(mux_b_enable_pin, false);
}

// Set mux to specific channel
void write_mux_address(const uint8_t select_pins[4], uint8_t channel) {
  for (uint8_t bit = 0; bit < 4; ++bit) {
    digitalWrite(select_pins[bit], (channel >> bit) & 0x01U ? HIGH : LOW);
  }
}

// Select a specific cell and configure muxes automatically
void select_cell(uint8_t row, uint8_t col) {
  disable_muxes(); // Disable muxes befor changing channel
  write_mux_address(mux_a_select_pins, row);
  write_mux_address(mux_b_select_pins, col);
  delayMicroseconds(address_settling_delay_us);

  set_mux_enabled(mux_b_enable_pin, true);
  set_mux_enabled(mux_a_enable_pin, true);

  delayMicroseconds(mux_settling_delay_us);
}

// Read specific cell
uint16_t read_cell(uint8_t row, uint8_t col) {
  select_cell(row, col);

  (void)analogReadMilliVolts(adc_read_pin); // Remove any charge from last cell
  delayMicroseconds(adc_resample_delay_us);

  // Measure average of cell
  uint32_t raw_sum = 0;
  for (uint8_t sample = 0; sample < samples_per_cell; ++sample) {
    if (read_linear_voltage) {
      raw_sum += analogReadMilliVolts(adc_read_pin);
    }
    else {
      raw_sum += analogRead(adc_read_pin);
    }
    if (sample + 1 < samples_per_cell) {
      delayMicroseconds(adc_resample_delay_us);
    }
  }
  disable_muxes();
  
  const uint32_t average_raw = raw_sum / samples_per_cell;

  uint16_t normalized_raw;
  if (read_linear_voltage) {
      normalized_raw = (average_raw * normalized_max) / adc_linear_max;
  }
  else {
      normalized_raw = (average_raw * normalized_max) / adc_raw_max;
  }

  return normalized_raw;
}

// Measure whole grid
void scan_grid() {
  for (uint8_t row = 0; row < grid_rows; ++row) {
    for (uint8_t col = 0; col < grid_cols; ++col) {
      const float measurement = read_cell(row, col);
      if (smoothing_enabled && filter_has_started) {
        filtered_grid[row][col] = smoothing_strength * filtered_grid[row][col] + (1.0f - smoothing_strength) * measurement;
      } else {
        filtered_grid[row][col] = measurement;
      }
    }
  }

  filter_has_started = true; 
  disable_muxes();
}

// Build data frame for MQTT and Serial transfer
void build_frame_text() {
  frame_text[0] = '\0';  // Start with an empty string
  char value_text[8];    // Holds one formatted numbe (ex: "1000")

  for (uint8_t row = 0; row < grid_rows; ++row) {
    for (uint8_t col = 0; col < grid_cols; ++col) {
      if (row != 0 || col != 0) {
        strcat(frame_text, ","); // Concatenate to add comma at the end
      }
      const int value = static_cast<int>(filtered_grid[row][col] + 0.5f); // more precise rounding
      snprintf(value_text, sizeof(value_text), "%d", value); // format int to string
      strcat(frame_text, value_text); // Add value_string to end of frame_text
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

// Try to reconnect if no MQTT and rung MQTT loop
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
  if (serial_debug) Serial.println("MQTT not connected, will try again ...");
}

// Build latest frame and send over MQTT
void send_frame() {
  build_frame_text();

  if (mqtt_client.connected()) {
    mqtt_client.publish(mqtt_topic, frame_text, true);
    if (serial_debug) Serial.println("MQTT frame sent");
  }

  if (send_frame_serial) {
    Serial.println(frame_text);
    if (serial_debug) Serial.println("Serial frame sent");
  }
}

// Print current estimated fps
void print_fps(uint32_t loop_time_ms) {
  static uint8_t frame_count = 0;
  static uint32_t time_sum_ms = 0;

  time_sum_ms += loop_time_ms;
  frame_count ++;
  if (frame_count >= 10) {
    const float avg_loop_ms = time_sum_ms / static_cast<float>(frame_count);
    const float fps = 1000.0f / avg_loop_ms;
    Serial.printf("FPS: %.2f \n", fps);
    frame_count = 0;
    time_sum_ms = 0;
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("Smartmat Resistive V1");

  // Start with muxes off
  configure_output_pin(mux_a_enable_pin, HIGH);
  configure_output_pin(mux_b_enable_pin, HIGH);
  for (uint8_t bit = 0; bit < 4; ++bit) {
    configure_output_pin(mux_a_select_pins[bit], LOW);
    configure_output_pin(mux_b_select_pins[bit], LOW);
  }

  // Configure ADC pin
  pinMode(adc_read_pin, INPUT);
  analogReadResolution(12);
  if (!read_linear_voltage) {
     analogSetPinAttenuation(adc_read_pin, ADC_11db);
  }

  WiFi.mode(WIFI_STA);
  mqtt_client.setServer(mqtt_broker_ip, mqtt_port);
  mqtt_client.setBufferSize(mqtt_packet_buffer_size);

  delay(200);
  Serial.println("Boot OK");
}

void loop() {
  const uint32_t frame_started_ms = millis();

  maintain_wifi();
  maintain_mqtt();

  scan_grid();
  send_frame();

  // Delay if needed to achieve desired fps
  const uint32_t elapsed_ms = millis() - frame_started_ms;
  if (elapsed_ms < frame_interval_ms) {
    delay(frame_interval_ms - elapsed_ms);
  }
  if (serial_debug) print_fps(millis() - frame_started_ms);
}
