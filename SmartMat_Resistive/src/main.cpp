#include "Arduino.h"

// CONFIG
const int resistor_val = 0; // for voltage divider in Ohms

const bool enable_lowpass = true;
const float lowpass_alpha = 0.7; // 0.9 = heavy lowpass, 0.1 = small lowpass 

const int total_average_readings = 4;
int count_average_readings = 0;

const long mux_settling_delay = 10; // us 
const int ADC_read_pin = 34;
const int row_mux_s0 = 13, row_mux_s1 = 14, row_mux_s2 = 27, row_mux_s3 = 26; // row_mux_sig = 3.3V, row_mux_en = GND
const int col_mux_s0 = 25, col_mux_s1 = 33, col_mux_s2 = 32, col_mux_s3 = 16; // col_mux_sig = voltage divider, col_mux_en = GND

// VARIABLES 
const int total_rows = 16, total_cols = 15;
float sensor_grid[total_rows][total_cols];
float final_sensor_grid[total_rows][total_cols];

// SETUP
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("Booting ...");

  // pin setup
  pinMode(ADC_read_pin, INPUT);

  pinMode(row_mux_s0, OUTPUT);
  pinMode(row_mux_s1, OUTPUT);
  pinMode(row_mux_s2, OUTPUT);
  pinMode(row_mux_s3, OUTPUT);

  pinMode(col_mux_s0, OUTPUT);
  pinMode(col_mux_s1, OUTPUT);
  pinMode(col_mux_s2, OUTPUT);
  pinMode(col_mux_s3, OUTPUT);

  Serial.println("Boot OK");
}

// FUNCTIONS
void set_mux(int r, int c) {
  digitalWrite(row_mux_s0, r & 0b0001);
  digitalWrite(row_mux_s1, (r >> 1) & 0b0001);
  digitalWrite(row_mux_s2, (r >> 2) & 0b0001);
  digitalWrite(row_mux_s3, (r >> 3) & 0b0001);

  digitalWrite(col_mux_s0, c & 0b0001);
  digitalWrite(col_mux_s1, (c >> 1) & 0b0001);
  digitalWrite(col_mux_s2, (c >> 2) & 0b0001);
  digitalWrite(col_mux_s3, (c >> 3) & 0b0001);
}
void measure_grid() {
  for (int row = 0; row < total_rows; row++) {
    for (int col = 0; col < total_cols; col++) {
      set_mux(row, col);
      
      delayMicroseconds(mux_settling_delay);

      int measurement = map(analogReadMilliVolts(ADC_read_pin),0,3300,0,1000); // normalize measurements
      sensor_grid[row][col] += measurement;
    }
  }
  count_average_readings++;
}

void calculate_and_print_final_grid() {
  Serial.println();
  for (int row = 0; row < total_rows; row++) {
    for (int col = 0; col < total_cols; col++) {

      int final_measurement = sensor_grid[row][col] / total_average_readings;

      if (enable_lowpass) {
        final_sensor_grid[row][col] = lowpass_alpha * final_sensor_grid[row][col] + (1 - lowpass_alpha) * final_measurement;
      }
      else {
        final_sensor_grid[row][col] = final_measurement;
      }

      Serial.print(final_sensor_grid[row][col]);
      Serial.print(",");
    }
  }
}

void reset_sensor_grid() {
  for (int row = 0; row < total_rows; row++) {
    for (int col = 0; col < total_cols; col++) {
      sensor_grid[row][col] = 0;
    }
  }
}

// LOOP
void loop() {

  // take measurements of sensors
  measure_grid();

  // average, lowpass for final grid
  if (count_average_readings >= total_average_readings) {
    calculate_and_print_final_grid();
    reset_sensor_grid();
    count_average_readings = 0;
  }

}