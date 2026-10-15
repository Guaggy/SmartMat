### Notes for future improvements and bugfixes

- Not verified on real hardware: `mux_settling_delay_us` (100 us) and the ADC calibration assumptions; check for
  ghosting between neighbouring cells and the real achieved frame rate (`serial_debug` prints it, but keep
  `serial_debug` off while `send_frame_serial` is on).
- Serial output is limited to 5 fps (115200 baud cannot carry 10 fps of 240 values); MQTT keeps 10 fps. A higher
  serial baud would need a matching protocol profile on the Pi side.
- No `status` (last-will) topic yet, unlike `ESP32_China`: add it if the Pi should show this mat as offline.
- Wi-Fi/MQTT reconnects run in the same loop as the scan (fine at 10 fps, unlike the S3 bridge which needed its
  own task).
