"""Reads frames from a USB-serial mat (resistive ESP32 text, or the Maxrays 20x20 binary stream)"""

import math
import threading
import time
from collections import namedtuple
from pathlib import Path

import serial
import serial.tools.list_ports

import config
from general import LatestFrame, parse_frame_text, parse_frame_text_with_reason, scale_to_app_range
from processing.source_quality import SourceQuality
from config import BAUD_RATE, VALUE_MAX_DEFAULT
from sources.maxrays import MaxraysDecoder

RAW_CAPTURE_S = 5.0  # default length of a raw byte capture
POLL_INTERVAL_S = 0.02  # How often the background thread checks for new bytes
MAX_RECEIVE_BUFFER_BYTES = 16 * 1024  # Guards against no new line
RX_BUFFER_BYTES = 256 * 1024  # driver receive buffer asked for (Windows), ~2.8 s at 921600 baud

TEXT_PROFILE = "ESP32 text (115200)"
MAXRAYS_PROFILE = "Maxrays 20x20 (921600)"
DEFAULT_SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)  # config.py's own size (TOTAL_* are overwritten at runtime)
# shape/mat_id None = the text profile: config grid size, port name as mat id.
# model / size_mm = preset: the mat's name and its default sensing size (width, height) in mm, used when the mat's
# own profile has no size. MC266 datasheet: 20x20, 5 V / 200 mA, 800 Pa - 200 kPa, about +/-10 % at best (repeatability
# +/-15 %), not suitable for weighing. size_mm was measured from the datasheet drawing (see notes.md), approximate.
PROFILES = {
    TEXT_PROFILE: {"baud": BAUD_RATE, "shape": None, "value_max": VALUE_MAX_DEFAULT, "mat_id": None,
                   "vendor": None, "model": None, "size_mm": None},
    MAXRAYS_PROFILE: {"baud": 921600, "shape": (20, 20), "value_max": 255, "mat_id": "maxrays-usb",
                      "vendor": "Maxrays", "model": "MC266", "size_mm": (343.0, 358.0)},
}

Port = namedtuple("Port", "device label")
RawCapture = namedtuple("RawCapture", "path size headers error")  # headers = count of A5 5A seen


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


def _read_latest_frame(connection, receive_buffer, quality=None, shape=None):
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
            grid, reason = parse_frame_text_with_reason(raw_line.decode("ascii"), shape=shape)
        except UnicodeDecodeError:
            grid, reason = None, "malformed"
        if quality is not None:
            quality.packet(reason, timestamp=False)
        if grid is not None:
            if newest is not None and quality is not None:
                quality.drop()
            newest = grid
    return newest


def _read_maxrays_frames(connection, decoder, quality):
    """Feed waiting bytes to the decoder and return every decoded raw grid (each counts as received/valid)"""

    available = connection.in_waiting
    if not available:
        return []
    invalid = decoder.stats.invalid_frames
    frames = decoder.feed(connection.read(available))
    # only a false header / truncated packet is malformed; filler or idle bytes between frames are not
    # (they stay visible as discarded bytes in serial_stats), and a poll with a valid frame is not either
    if decoder.stats.invalid_frames > invalid and not frames:
        quality.packet("malformed", timestamp=False)
    for _ in frames:
        quality.packet(None, timestamp=False)
    return frames


class _Tap:
    """What the read helpers see as the connection: passes reads through and feeds them to the capture/counter"""

    def __init__(self, source):
        self._source = source

    @property
    def in_waiting(self):
        return self._source._connection.in_waiting

    def read(self, count):
        data = self._source._connection.read(count)
        self._source._capture_step(data)
        return data


def _target_fps(value, default=10.0):
    """Config value -> averaging rate: None / not a number -> default, 0 or negative -> 0 (off)"""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(value, 0.0) if math.isfinite(value) else default


class SerialSource:
    """Grids from a USB-serial mat on a background thread, decoded per protocol profile"""

    def __init__(self, port, profile=TEXT_PROFILE, clock=time.monotonic):
        self.port = port
        self.profile = profile
        spec = PROFILES[profile]
        self.baud = spec["baud"]
        self.shape = spec["shape"] or DEFAULT_SHAPE
        self.value_max = spec["value_max"]
        self.mat_id = spec["mat_id"] or port
        self.vendor, self.model, self.default_size_mm = spec["vendor"], spec["model"], spec["size_mm"]  # preset (None for the text profile)
        self.latest = LatestFrame()
        self.quality = SourceQuality()
        self.decoder = MaxraysDecoder(*self.shape) if profile == MAXRAYS_PROFILE else None
        # Maxrays streams ~60 fps but the analysis windows are tuned for ~10: average down to this (0 = off)
        self.target_fps = _target_fps(getattr(config, "SERIAL_TARGET_FPS", 10)) if self.decoder is not None else 0
        self._clock = clock
        self._window = [None, 0.0, 0]  # averaging window: [start time, running sum of raw grids, frame count]
        self._connection = None
        self._tap = _Tap(self)
        self._lock = threading.Lock()
        self._bytes = 0  # every byte read from the port, for bytes/s
        self._out = 0  # grids handed to `latest` (after averaging), for the output rate
        self._rate_mark, self._bytes_per_s, self._out_per_s = (time.monotonic(), 0, 0), 0.0, 0.0
        self._capture = None  # running raw capture: [path, end time, bytearray, clock]
        self.capture_result = None  # RawCapture of the last finished capture
        self._receive_buffer = bytearray()
        self._thread = None
        self._running = False

    def start(self):
        """Open the port and start reading (raises if the port can't open)"""
        self._connection = serial.Serial(self.port, self.baud, timeout=0)  # 8-N-1
        if hasattr(self._connection, "set_buffer_size"):
            # Windows' default 4 KB driver buffer holds only ~45 ms at 921600 baud; a busy GUI overruns it
            self._connection.set_buffer_size(rx_size=RX_BUFFER_BYTES)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def start_raw_capture(self, path, seconds=RAW_CAPTURE_S, clock=time.monotonic):
        """Copy the exact bytes read from the port to path for `seconds`, then write the file"""
        with self._lock:
            self.capture_result = None
            self._capture = [Path(path), clock() + seconds, bytearray(), clock]

    @property
    def capturing(self):
        return self._capture is not None

    def _capture_step(self, data=b"", finish=False):
        """Add bytes to the running capture and finish it once its time is up (or now, if finish)"""
        with self._lock:
            self._bytes += len(data)
            capture = self._capture
            if capture is None:
                return
            capture[2].extend(data)
            if not finish and capture[3]() < capture[1]:
                return
            self._capture = None
            path, _, raw, _ = capture
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                error = None
            except OSError as exc:
                error = str(exc)
            self.capture_result = RawCapture(path, len(raw), raw.count(MaxraysDecoder.HEADER), error)

    def serial_stats(self):
        """Protocol, bytes/s, frames/s and the decoder's discarded/invalid counts (None = not applicable)"""
        now = time.monotonic()
        mark_time, mark_bytes, mark_out = self._rate_mark
        if now - mark_time >= 1.0:
            self._bytes_per_s = (self._bytes - mark_bytes) / (now - mark_time)
            self._out_per_s = (self._out - mark_out) / (now - mark_time)
            self._rate_mark = (now, self._bytes, self._out)
        quality = self.quality.snapshot()
        stats = self.decoder.stats if self.decoder is not None else None
        return {"protocol": self.profile, "bytes_per_s": self._bytes_per_s, "frames_per_s": quality["rate_hz"],
                "output_per_s": self._out_per_s,  # grids per second after averaging (frames_per_s = decoded)
                "discarded_bytes": stats.bytes_discarded if stats else None,
                "invalid_frames": stats.invalid_frames if stats else quality["malformed"]}

    def _average(self, frames):
        """Add decoded grids to the window; return its mean once it is 1/target_fps s old, else None"""
        now = self._clock()
        period = 1.0 / self.target_fps
        if frames and self._window[0] is None:
            self._window[0] = now  # the window starts with its first frame
        for grid in frames:
            self._window[1] = self._window[1] + grid  # float after the first add
            self._window[2] += 1
        if self._window[2] and now - self._window[0] >= period:
            mean = self._window[1] / self._window[2]
            # the next window starts where this one was due to end, not at the next poll with a frame:
            # restarting from the next frame added a poll (+ sleep jitter) to every window, ~7.7 fps for 10
            start = self._window[0] + period
            self._window = [start if now - start < period else None, 0.0, 0]
            return mean
        return None

    def _poll_once(self):
        if self.decoder is not None:
            frames = _read_maxrays_frames(self._tap, self.decoder, self.quality)
            if self.target_fps > 0:
                grid = self._average(frames)  # merged frames are not drops
            else:
                self.quality.drop(max(len(frames) - 1, 0))
                grid = frames[-1] if frames else None
        else:
            grid = _read_latest_frame(self._tap, self._receive_buffer, self.quality, self.shape)
        self._capture_step()  # also ends a capture when the port went quiet
        if grid is not None:
            self._out += 1
            if self.latest.set(scale_to_app_range(grid, self.value_max)):
                self.quality.drop()

    def _run(self):
        try:
            while self._running:
                self._poll_once()
                time.sleep(POLL_INTERVAL_S)
        finally:  # stop() or the port vanished: keep the bytes captured so far
            self._capture_step(finish=True)

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._connection is not None:
            self._connection.close()
