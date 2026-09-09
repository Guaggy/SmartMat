#include <Arduino.h>

namespace {

// This pin map matches the final wiring table. MUX A drives the 16-line
// sensor axis; MUX B reads the 15-line axis through GPIO34.
constexpr uint8_t ADC_READ_PIN = 34;

constexpr uint8_t MUX_A_EN_PIN = 18;
constexpr uint8_t MUX_A_SELECT_PINS[4] = {19, 21, 22, 23};

constexpr uint8_t MUX_B_EN_PIN = 27;
constexpr uint8_t MUX_B_SELECT_PINS[4] = {26, 25, 33, 32};

constexpr uint8_t TOTAL_ROWS = 16;
constexpr uint8_t TOTAL_COLS = 15;

constexpr uint8_t SAMPLES_PER_CELL = 4;
constexpr uint16_t ADDRESS_SETTLING_DELAY_US = 2;
// This assumes there is no 10 nF capacitor directly on GPIO34. If one is
// fitted, start around 500 us and tune downward while watching for ghosting.
constexpr uint16_t MUX_SETTLING_DELAY_US = 100;
constexpr uint16_t ADC_RESAMPLE_DELAY_US = 5;

constexpr uint16_t ADC_RAW_MAX = 4095;
constexpr uint16_t NORMALIZED_MAX = 1000;

constexpr bool ENABLE_LOWPASS = true;
constexpr float LOWPASS_ALPHA = 0.7f;

// Serial output is the practical speed limit, but this also prevents the
// firmware from producing more than ten frames per second.
constexpr uint32_t FRAME_INTERVAL_MS = 100;

float filtered_sensor_grid[TOTAL_ROWS][TOTAL_COLS] = {};
bool filter_initialized = false;

void configureOutputPin(uint8_t pin, uint8_t initial_level) {
  // Preload the output latch before enabling the output driver. This keeps the
  // active-low MUX enable pins HIGH while the board starts.
  digitalWrite(pin, initial_level);
  pinMode(pin, OUTPUT);
}

void setMuxEnabled(uint8_t enable_pin, bool enabled) {
  digitalWrite(enable_pin, enabled ? LOW : HIGH);
}

void disableMuxes() {
  setMuxEnabled(MUX_A_EN_PIN, false);
  setMuxEnabled(MUX_B_EN_PIN, false);
}

void writeMuxAddress(const uint8_t select_pins[4], uint8_t channel) {
  for (uint8_t bit = 0; bit < 4; ++bit) {
    digitalWrite(select_pins[bit], (channel >> bit) & 0x01U ? HIGH : LOW);
  }
}

void selectCell(uint8_t row, uint8_t col) {
  disableMuxes();
  writeMuxAddress(MUX_A_SELECT_PINS, row);
  writeMuxAddress(MUX_B_SELECT_PINS, col);
  delayMicroseconds(ADDRESS_SETTLING_DELAY_US);

  // Connect the measurement side before connecting the 3.3 V drive side.
  setMuxEnabled(MUX_B_EN_PIN, true);
  setMuxEnabled(MUX_A_EN_PIN, true);
  delayMicroseconds(MUX_SETTLING_DELAY_US);
}

uint16_t readCell(uint8_t row, uint8_t col) {
  selectCell(row, col);

  // Discard the first conversion after changing channels so charge left from
  // the previous cell has less influence on the result.
  (void)analogRead(ADC_READ_PIN);
  delayMicroseconds(ADC_RESAMPLE_DELAY_US);

  uint32_t raw_sum = 0;
  for (uint8_t sample = 0; sample < SAMPLES_PER_CELL; ++sample) {
    raw_sum += analogRead(ADC_READ_PIN);
    if (sample + 1 < SAMPLES_PER_CELL) {
      delayMicroseconds(ADC_RESAMPLE_DELAY_US);
    }
  }

  disableMuxes();

  const uint32_t average_raw =
      (raw_sum + SAMPLES_PER_CELL / 2U) / SAMPLES_PER_CELL;
  return static_cast<uint16_t>(
      (average_raw * NORMALIZED_MAX + ADC_RAW_MAX / 2U) / ADC_RAW_MAX);
}

void scanGrid() {
  for (uint8_t row = 0; row < TOTAL_ROWS; ++row) {
    for (uint8_t col = 0; col < TOTAL_COLS; ++col) {
      const float measurement = readCell(row, col);
      if (ENABLE_LOWPASS && filter_initialized) {
        filtered_sensor_grid[row][col] =
            LOWPASS_ALPHA * filtered_sensor_grid[row][col] +
            (1.0f - LOWPASS_ALPHA) * measurement;
      } else {
        filtered_sensor_grid[row][col] = measurement;
      }
    }
  }

  filter_initialized = true;
  disableMuxes();
}

void printGrid() {
  bool first_value = true;
  for (uint8_t row = 0; row < TOTAL_ROWS; ++row) {
    for (uint8_t col = 0; col < TOTAL_COLS; ++col) {
      if (!first_value) {
        Serial.print(',');
      }
      first_value = false;

      // Integer output keeps each 240-value frame small.
      Serial.print(static_cast<int>(filtered_sensor_grid[row][col] + 0.5f));
    }
  }
  Serial.println();
}

}  // namespace

void setup() {
  Serial.begin(115200);

  configureOutputPin(MUX_A_EN_PIN, HIGH);
  configureOutputPin(MUX_B_EN_PIN, HIGH);

  for (uint8_t bit = 0; bit < 4; ++bit) {
    configureOutputPin(MUX_A_SELECT_PINS[bit], LOW);
    configureOutputPin(MUX_B_SELECT_PINS[bit], LOW);
  }

  pinMode(ADC_READ_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(ADC_READ_PIN, ADC_11db);

  delay(200);
  Serial.println("# Boot OK: SmartMat 16x15");
}

void loop() {
  const uint32_t frame_started_ms = millis();

  scanGrid();
  printGrid();

  const uint32_t elapsed_ms = millis() - frame_started_ms;
  if (elapsed_ms < FRAME_INTERVAL_MS) {
    delay(FRAME_INTERVAL_MS - elapsed_ms);
  }
}
