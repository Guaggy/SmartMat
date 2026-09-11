"""Reads frames from the ESP32 over MQTT"""

import paho.mqtt.client as mqtt
import config
from general import LatestFrame, parse_frame_text

def parse_frame(payload):
    """Decode one MQTT payload and convert it to grid"""

    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        return None
    return parse_frame_text(text)


class MqttSource:
    """Streams grids from the ESP32 over MQTT, using paho network thread"""

    def __init__(self):
        self.latest = LatestFrame()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smartmat-pi")
        self._client.username_pw_set(config.mqtt_username, config.mqtt_password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        print(f"Connected to {config.broker_host}:{config.broker_port}, subscribing to {config.mqtt_topic}")
        client.subscribe(config.mqtt_topic)

    def _on_message(self, client, userdata, message):
        grid = parse_frame(message.payload)
        if grid is not None:
            self.latest.set(grid)

    def start(self):
        """Connect and start paho's background network loop (raises if unreachable)"""
        self._client.connect(config.broker_host, config.broker_port)
        self._client.loop_start()

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
