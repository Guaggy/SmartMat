"""Reads frames from the ESP32 mats over MQTT"""

import math
import re
import threading

import paho.mqtt.client as mqtt
import config
from config import VALUE_MAX_DEFAULT
from general import LatestFrame, parse_frame_text, parse_frame_text_with_reason, scale_to_app_range
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
    """Convert a meta message to (chip_id, rows, cols, value_max, model, size_mm); None if invalid.

    Accepted forms: "<chip_id>,<rows>,<cols>" (resistive firmware, value_max 1000),
    "<chip_id>,<rows>,<cols>,<value_max>" and
    "<chip_id>,<rows>,<cols>,<value_max>,<model>,<width_mm>,<height_mm>".
    model / size_mm are None for the shorter forms (a preset the mat does not announce).
    """

    pieces = [piece.strip() for piece in text.split(",")]
    if len(pieces) not in (3, 4, 7) or not pieces[0].isalnum():  # isalnum also keeps topic wildcards out
        return None
    model = size_mm = None
    try:
        rows, cols = int(pieces[1]), int(pieces[2])
        value_max = int(pieces[3]) if len(pieces) > 3 else VALUE_MAX_DEFAULT
        if len(pieces) == 7:
            model = pieces[4]
            size_mm = (float(pieces[5]), float(pieces[6]))
    except ValueError:
        return None
    if not (1 <= rows <= MAX_GRID_SIDE and 1 <= cols <= MAX_GRID_SIDE) or value_max < 1:
        return None
    if model is not None and (not re.fullmatch(r"[A-Za-z0-9_-]+", model)
                              or not all(math.isfinite(side) and side > 0 for side in size_mm)):
        return None
    return pieces[0], rows, cols, value_max, model, size_mm


class MqttSource:
    """Streams grids from one ESP32 mat over MQTT, using paho network thread.

    Without a chip_id it only listens for every mat's metadata (for the device list).
    """

    def __init__(self, chip_id=None):
        self.chip_id = chip_id
        self.mats = {}  # chip_id -> (rows, cols) for every mat the broker has metadata for
        self.value_maxes = {}  # chip_id -> raw full scale (kept apart so mats stays (rows, cols))
        self.presets = {}  # chip_id -> (model, (width_mm, height_mm)) for mats whose meta announces one
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
    def value_max(self):
        """Raw full scale reported by the selected mat"""
        return self.value_maxes.get(self.chip_id, VALUE_MAX_DEFAULT)

    @property
    def model(self):
        """Model name the selected mat announces in its meta, None if it does not"""
        return self.presets.get(self.chip_id, (None, None))[0]

    @property
    def default_size_mm(self):
        """Sensing size (width, height) mm the selected mat announces, None if it does not"""
        return self.presets.get(self.chip_id, (None, None))[1]

    @property
    def mat_id(self):
        return self.chip_id

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
                self.value_maxes[meta[0]] = meta[3]
                self.mats[meta[0]] = meta[1:3]
                if meta[4] is None:
                    self.presets.pop(meta[0], None)  # newer meta without a preset replaces an older one
                else:
                    self.presets[meta[0]] = meta[4:6]
                if meta[0] == self.chip_id:
                    self._meta_seen.set()
            return
        if message.retain or self.shape is None:
            return  # a retained frame is stale after a reconnect and must not look live; or no metadata yet
        grid, reason = ((None, "malformed") if text is None
                        else parse_frame_text_with_reason(text, self.value_max, self.shape))
        self.quality.packet(reason, timestamp=False)
        if grid is not None:
            if self.latest.set(scale_to_app_range(grid, self.value_max)):
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
