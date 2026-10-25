SM_Launch - SmartMat on this Raspberry Pi
=========================================

Icons in this folder (double-click):
  1 Web dashboard (fullscreen)     The touchscreen dashboard, same as at boot.
                                   Close it: HOLD the logo 3 s, or tap the logo 5 times in 4 s (or Alt+F4).
                                   One tap on the logo = back to the main heatmap.
  2 Desktop dashboard (advanced)   The full desktop app: calibration, analysis, recordings.
                                   Close the web dashboard first (this icon does it for you).
                                   First time: Engineering > Connection > host localhost, user/password smartmat, source MQTT.
  3 SmartMat config (terminal)     Menu for everything else (below). Same as typing  smartmat  in a terminal.

What runs in the background (always, by itself):
  mosquitto        the MQTT broker the mats talk to          (10.0.0.15:1883, user smartmat)
  smartmat-server  analysis + alerts + web page on port 8000 (http://<pi-ip>:8000)
Mats (ESP32 boards) join over WiFi; an ESP32 on the Pi's USB is only power/log/flashing.

Terminal commands (smartmat help lists them all):
  smartmat status                   one-page report: services, mats, ESP32, network, updates, temperature
  smartmat web start|stop|restart   the fullscreen web dashboard
  smartmat boot web on|off          start the web dashboard at boot or not
  smartmat sim demo 2|off           two fake mats inside the server
  smartmat sim replay on|off        replay a recorded seat as a fake mat over MQTT
  smartmat restart server|web|broker|all     services only, no reboot
  smartmat reboot                   restart the whole Pi
  smartmat update                   git pull, refresh launchers, restart the server
  smartmat logs server|broker       recent log lines
  smartmat mats [forget <id>]       list mats / clear a retired mat from the broker
  smartmat esp32 reset|log|flash real|sim|dump|resistive
  smartmat backup                   save users, database and profiles to your home folder

Reach the dashboard from another device: http://<pi-ip>:8000 (smartmat ip shows the addresses; Tailscale works from anywhere).
Settings (alerts, mat names, users) are in the dashboard under the settings icon; changes need an administrator PIN.
If something is wrong: smartmat status, then smartmat logs server.
