// B1 toolchain spike: ESP32-S3 USB host reads a CH34x serial device (the mat)
// and logs once a second how many bytes arrived plus the first 16 bytes in hex.
// WiFi + PubSubClient are linked in only to prove they build in the same project.

#include <Arduino.h>
#include <EspUsbHost.h>
#include <PubSubClient.h>
#include <WiFi.h>

const uint32_t debug_baud = 115200;
const uint32_t mat_baud = 921600;          // CH340, 8-N-1 (library default framing)
const size_t usb_rx_buffer_size = 8192;    // default 512 B is ~5 ms at 921600
const uint32_t log_interval_ms = 1000;

EspUsbHost usb;
EspUsbHostCdcSerial mat_serial(usb);
WiFiClient wifi_client;
PubSubClient mqtt_client(wifi_client);

uint32_t byte_count = 0;
uint8_t first_bytes[16];
uint8_t first_count = 0;
uint32_t last_log_ms = 0;

void setup() {
  Serial.begin(debug_baud);

  WiFi.mode(WIFI_STA);  // link check only, no connect in the spike
  mqtt_client.setBufferSize(2048);

  usb.onDeviceConnected([](const EspUsbHostDeviceInfo &device) {
    Serial.print("USB connected: ");
    espUsbHostPrint(device);
  });
  usb.onDeviceDisconnected([](const EspUsbHostDeviceInfo &device) {
    Serial.print("USB disconnected: ");
    espUsbHostPrint(device);
  });

  // The library rebinds the port on replug, so reconnect needs no extra code.
  mat_serial.setRxBufferSize(usb_rx_buffer_size);
  mat_serial.begin(mat_baud);
  if (!usb.begin()) {
    Serial.printf("usb.begin() failed: %s\n", usb.lastErrorName());
  }
}

void loop() {
  while (mat_serial.available() > 0) {
    const uint8_t value = mat_serial.read();
    if (first_count < sizeof(first_bytes)) first_bytes[first_count++] = value;
    ++byte_count;
  }

  const uint32_t now = millis();
  if (now - last_log_ms >= log_interval_ms) {
    last_log_ms = now;
    Serial.printf("[%s] %lu bytes/s:", mat_serial.connected() ? "up" : "down",
                  static_cast<unsigned long>(byte_count));
    for (uint8_t i = 0; i < first_count; ++i) Serial.printf(" %02X", first_bytes[i]);
    Serial.println();
    byte_count = 0;
    first_count = 0;
  }
  delay(1);
}
