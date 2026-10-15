"""Reads frames from a USB-serial mat (resistive ESP32 text, or the Maxrays 20x20 binary stream)"""

import threading
import time
from collections import namedtuple

import serial
import serial.tools.list_ports

import config
from general import LatestFrame, parse_frame_text, parse_frame_text_with_reason, scale_to_app_range
from processing.source_quality import SourceQuality
from config import BAUD_RATE, VALUE_MAX_DEFAULT
from sources.maxrays import MaxraysDecoder

POLL_INTERVAL_S = 0.02  # How often the background thread checks for new bytes
MAX_RECEIVE_BUFFER_BYTES = 16 * 1024  # Guards against no new line

TEXT_PROFILE = "ESP32 text (115200)"
MAXRAYS_PROFILE = "Maxrays 20x20 (921600)"
DEFAULT_SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)  # config.py's own size (TOTAL_* are overwritten at runtime)
# shape/mat_id None = the text profile: config grid size, port name as mat id
PROFILES = {
    TEXT_PROFILE: {"baud": BAUD_RATE, "shape": None, "value_max": VALUE_MAX_DEFAULT, "mat_id": None},
    MAXRAYS_PROFILE: {"baud": 921600, "shape": (20, 20), "value_max": 255, "mat_id": "maxrays-usb"},
}

Port = namedtuple("Port", "device label")


def list_ports():
    """Return the available serial ports as Port(device, label), label "COM3 - USB-SERIAL CH340" """

    ports = []
    for port in serial.tools.list_ports.comports():
        description = (port.description or "").replace(f" ({port.device})", "")
        label = f"{port.device} - {description}" if description and description != "n/a" else port.device
        ports.append(Port(port.device, label))
    return ports


def parse_frame(raw_line):
    """Decode one serial line and convert to grid"""

    try:
        text = raw_line.decode("ascii")
    except UnicodeDecodeError:
        return None
    return parse_frame_text(text)


def _read_latest_frame(connection, receive_buffer, quality=None):
    """Empty serial data, keep any partial line, and return the newest grid"""

    available = connection.in_waiting
    if available:
        receive_buffer.extend(connection.read(available))

    last_newline = receive_buffer.rfind(b"\n")
    if last_newline < 0:
        if len(receive_buffer) > MAX_RECEIVE_BUFFER_BYTES:
            receive_buffer.clear()
            if quality is not None:
                quality.packet("malformed", timestamp=False)
        return None

    complete_data = bytes(receive_buffer[:last_newline])
    del receive_buffer[: last_newline + 1]

    newest = None
    for raw_line in complete_data.split(b"\n"):
        try:
            grid, reason = parse_frame_text_with_reason(raw_line.decode("ascii"))
        except UnicodeDecodeError:
            grid, reason = None, "malformed"
        if quality is not None:
            quality.packet(reason, timestamp=False)
        if grid is not None:
            if newest is not None and quality is not None:
                quality.drop()
            newest = grid
    return newest


def _read_latest_maxrays(connection, decoder, quality):
    """Feed waiting bytes to the decoder and return the newest raw grid (earlier ones count as dropped)"""

    available = connection.in_waiting
    if not available:
        return None
    discarded = decoder.stats.bytes_discarded
    frames = decoder.feed(connection.read(available))
    if decoder.stats.bytes_discarded > discarded:  # garbage or a false header
        quality.packet("malformed", timestamp=False)
    for _ in frames:
        quality.packet(None, timestamp=False)
    quality.drop(max(len(frames) - 1, 0))
    return frames[-1] if frames else None


class SerialSource:
    """Grids from a USB-serial mat on a background thread, decoded per protocol profile"""

    def __init__(self, port, profile=TEXT_PROFILE):
        self.port = port
        self.profile = profile
        spec = PROFILES[profile]
        self.baud = spec["baud"]
        self.shape = spec["shape"] or DEFAULT_SHAPE
        self.value_max = spec["value_max"]
        self.mat_id = spec["mat_id"] or port
        self.latest = LatestFrame()
        self.quality = SourceQuality()
        self.decoder = MaxraysDecoder(*self.shape) if profile == MAXRAYS_PROFILE else None
        self._connection = None
        self._receive_buffer = bytearray()
        self._thread = None
        self._running = False

    def start(self):
        """Open the port and start reading (raises if the port can't open)"""
        self._connection = serial.Serial(self.port, self.baud, timeout=0)  # 8-N-1
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _poll_once(self):
        if self.decoder is not None:
            grid = _read_latest_maxrays(self._connection, self.decoder, self.quality)
        else:
            grid = _read_latest_frame(self._connection, self._receive_buffer, self.quality)
        if grid is not None:
            if self.latest.set(scale_to_app_range(grid, self.value_max)):
                self.quality.drop()

    def _run(self):
        while self._running:
            self._poll_once()
            time.sleep(POLL_INTERVAL_S)

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._connection is not None:
            self._connection.close()
