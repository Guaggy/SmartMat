"""Reads frames from the ESP32 over USB-serial connection"""

import threading
import time
import serial
import serial.tools.list_ports

from general import LatestFrame, parse_frame_text, parse_frame_text_with_reason
from processing.source_quality import SourceQuality
from config import BAUD_RATE

POLL_INTERVAL_S = 0.02  # How often the background thread checks for new bytes
MAX_RECEIVE_BUFFER_BYTES = 16 * 1024  # Guards against no new line


def list_ports():
    """Return the available serial ports"""

    return list(serial.tools.list_ports.comports())


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


class SerialSource:
    """Grids from the ESP32 over USB serial on a background thread"""

    def __init__(self, port):
        self.port = port
        self.latest = LatestFrame()
        self.quality = SourceQuality()
        self._connection = None
        self._thread = None
        self._running = False

    def start(self):
        """Open the port and start reading (raises if the port can't open)"""
        self._connection = serial.Serial(self.port, BAUD_RATE, timeout=0)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        receive_buffer = bytearray()
        while self._running:
            grid = _read_latest_frame(self._connection, receive_buffer, self.quality)
            if grid is not None:
                if self.latest.set(grid):
                    self.quality.drop()
            time.sleep(POLL_INTERVAL_S)

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._connection is not None:
            self._connection.close()
