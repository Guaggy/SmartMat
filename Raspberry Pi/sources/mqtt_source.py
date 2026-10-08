"""Reads frames from the ESP32 mats over MQTT"""

import threading

import paho.mqtt.client as mqtt
import config
from general import LatestFrame, parse_frame_text, parse_frame_text_with_reason
from processing.source_quality import SourceQuality

TOPIC_PREFIX = "smartmat"  # must match mqtt_topic_prefix in ESP32/src/main.cpp
META_TIMEOUT_S = 3.0       # how long start() waits for the selected mat's metadata
MAX_GRID_SIDE = 255        # the ESP32 keeps rows/cols in a uint8

def parse_frame(payload):
    """Decode one MQTT payload and convert it to grid"""

    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        return None
    return parse_frame_text(text)


def parse_meta(text):
    """Convert a "<chip_id>,<rows>,<cols>" meta payload to (chip_id, rows, cols), None if invalid"""

    pieces = [piece.strip() for piece in text.split(",")]
    if len(pieces) != 3 or not pieces[0].isalnum():  # isalnum also keeps topic wildcards out
        return None
    try:
        rows, cols = int(pieces[1]), int(pieces[2])
    except ValueError:
        return None
    if not (1 <= rows <= MAX_GRID_SIDE and 1 <= cols <= MAX_GRID_SIDE):
        return None
    return pieces[0], rows, cols


class MqttSource:
    """Streams grids from one ESP32 mat over MQTT, using paho network thread.

    Without a chip_id it only listens for every mat's metadata (for the device list).
    """

    def __init__(self, chip_id=None):
        self.chip_id = chip_id
        self.mats = {}  # chip_id -> (rows, cols) for every mat the broker has metadata for
        self.latest = LatestFrame()
        self.quality = SourceQuality()
        self._connected = False
        self._meta_seen = threading.Event()
        # own client id for the listener, so it can stay up next to a streaming connection
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                   client_id="smartmat-pi" if chip_id else "smartmat-pi-discovery")
        self._client.username_pw_set(config.mqtt_username, config.mqtt_password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    @property
    def shape(self):
        """(rows, cols) reported by the selected mat, None until its metadata arrives"""
        return self.mats.get(self.chip_id)

    @property
    def state(self):
        """Startup progress: connecting -> awaiting_meta -> ready"""
        if not self._connected:
            return "connecting"
        if self.chip_id is not None and self.shape is None:
            return "awaiting_meta"
        return "ready"

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code.is_failure:
            print(f"MQTT broker refused the connection: {reason_code}")
            return
        self._connected = True
        print(f"Connected to {config.broker_host}:{config.broker_port}")
        client.subscribe(f"{TOPIC_PREFIX}/+/meta")  # retained, so known mats arrive right away
        if self.chip_id is not None:
            client.subscribe(f"{TOPIC_PREFIX}/{self.chip_id}/frame")

    def _on_message(self, client, userdata, message):
        try:
            text = message.payload.decode("ascii")
        except UnicodeDecodeError:
            text = None
        if message.topic.endswith("/meta"):
            meta = parse_meta(text or "")
            if meta is not None and message.topic == f"{TOPIC_PREFIX}/{meta[0]}/meta":
                self.mats[meta[0]] = meta[1:]
                if meta[0] == self.chip_id:
                    self._meta_seen.set()
            return
        if self.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            return  # the app has not switched to this mat's grid size yet
        grid, reason = (None, "malformed") if text is None else parse_frame_text_with_reason(text)
        self.quality.packet(reason, timestamp=False)
        if grid is not None:
            if self.latest.set(grid):
                self.quality.drop()

    def start(self):
        """Connect and start paho's background network loop.

        With a mat selected this raises if the broker is unreachable or the mat's metadata
        does not arrive. The metadata listener never blocks: paho keeps retrying in its thread.
        """
        if self.chip_id is None:
            self._client.connect_async(config.broker_host, config.broker_port)
            self._client.loop_start()
            return
        self._client.connect(config.broker_host, config.broker_port)
        self._client.loop_start()
        if not self._meta_seen.wait(META_TIMEOUT_S):
            state = self.state
            self.stop()
            raise TimeoutError(f"no metadata from mat {self.chip_id} ({state})")

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
