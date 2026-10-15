"""Decoder for the Maxrays 20x20 serial stream (A5 5A + 2-byte big-endian length + payload + 2 trailer bytes).

Values are returned raw (uint8, not scaled). The 2 trailer bytes are ignored: their checksum is undocumented.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class DecoderStats:
    bytes_received: int = 0
    frames_decoded: int = 0
    bytes_discarded: int = 0
    invalid_frames: int = 0


class MaxraysDecoder:
    HEADER = b"\xA5\x5A"

    def __init__(self, rows=20, cols=20):
        if rows <= 0 or cols <= 0:
            raise ValueError("rows and cols must be positive")
        self.rows, self.cols = rows, cols
        self.cells = rows * cols
        self.stats = DecoderStats()
        self._buf = bytearray()

    def feed(self, chunk):
        """Feed a serial chunk; return every complete frame as a uint8 (rows, cols) array."""
        data = bytes(chunk)
        self.stats.bytes_received += len(data)
        self._buf.extend(data)
        buf, st = self._buf, self.stats
        min_size = 4 + self.cells
        max_size = min_size + 32
        frames = []
        while True:
            start = buf.find(self.HEADER)
            if start < 0:
                # a trailing lone A5 may be half of the next header
                drop = len(buf) - (1 if buf.endswith(self.HEADER[:1]) else 0)
                del buf[:drop]
                st.bytes_discarded += drop
                break
            if start:
                del buf[:start]
                st.bytes_discarded += start
            if len(buf) < min_size:
                break
            # header-to-header spacing is the safest packet boundary; else use the declared length
            nxt = buf.find(self.HEADER, min_size)
            if 0 <= nxt <= max_size:
                size = nxt
            else:
                declared = int.from_bytes(buf[2:4], "big")
                if min_size <= declared <= max_size:
                    size = declared
                elif min_size <= declared + 4 <= max_size:
                    size = declared + 4
                else:  # false header
                    del buf[0]
                    st.bytes_discarded += 1
                    st.invalid_frames += 1
                    continue
                if len(buf) < size:
                    break
            frames.append(np.frombuffer(bytes(buf[4:min_size]), dtype=np.uint8).reshape(self.rows, self.cols).copy())
            del buf[:size]
        st.frames_decoded += len(frames)
        return frames
