"""Small command-line fallback for capturing an undocumented serial stream."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import time

import serial
from serial.tools import list_ports


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture raw bytes from the seat sensor")
    parser.add_argument("--port", help="Serial port, e.g. COM3")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not args.port:
        ports = list(list_ports.comports())
        if not ports:
            raise SystemExit("No serial ports found. Connect the sensor and try again.")
        print("Available ports:")
        for port in ports:
            print(f"  {port.device}: {port.description}")
        raise SystemExit("Run again with --port COMx")

    output = args.output or Path("recordings") / f"raw_{datetime.now():%Y%m%d_%H%M%S}.bin"
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Capturing {args.seconds:g} s from {args.port} at {args.baud} baud ...")
    data = bytearray()
    deadline = time.monotonic() + args.seconds
    with serial.Serial(args.port, args.baud, timeout=0.05) as sensor:
        sensor.reset_input_buffer()
        while time.monotonic() < deadline:
            data.extend(sensor.read(min(max(sensor.in_waiting, 1), 8192)))

    output.write_bytes(data)
    header_count = data.count(b"\xA5\x5A")
    print(f"Saved {len(data):,} bytes to {output}")
    print(f"Found {header_count} occurrence(s) of A5 5A")
    if len(data) >= 4 and data.find(b"\xA5\x5A") >= 0:
        start = data.find(b"\xA5\x5A")
        if start + 4 <= len(data):
            declared = int.from_bytes(data[start + 2 : start + 4], "big")
            print(f"First declared packet length: {declared} (0x{declared:04X})")


if __name__ == "__main__":
    main()
