"""Replay the bundled seat recording to an MQTT broker as a fake S3 mat, to test the MQTT path without hardware.

    python tools/publish_demo_mat.py                  # chip id demo-take1, broker from the app's settings
    python tools/publish_demo_mat.py --once --speed 2 --host 10.0.0.15

The broker login comes from the app's settings (Engineering > Connection, settings.json, config.py) or the
--host/--port/--user/--password options. Nothing is written to disk.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # the app folder, so its modules import from anywhere

import paho.mqtt.client as mqtt

import app_settings
from paths import resource_path
from processing.recording import load_session

SAMPLE = "samples/seat_take1.json"
STORED_MAX = 1000    # recordings keep values scaled 0-1000
VALUE_MAX = 255      # the S3 bridge sends 0-255 counts
META_TAIL = "20,20,255,MC266,343,358"  # rows, cols, value_max, model, width_mm, height_mm of the S3 bridge


def frame_payload(grid):
    """Row-major comma-separated 0-255 counts from a stored 0-1000 grid"""
    counts = (min(VALUE_MAX, max(0, round(value * VALUE_MAX / STORED_MAX))) for value in grid.ravel())
    return ",".join(str(count) for count in counts)


def replay(client, chip_id, frames, timestamps, speed=1.0, loop=True, sleep=time.sleep):
    """Publish meta + status (retained), then the frames at the recording's own pace; returns frames sent"""
    base = f"smartmat/{chip_id}"
    client.publish(f"{base}/meta", f"{chip_id},{META_TAIL}", qos=1, retain=True)
    client.publish(f"{base}/status", "online", qos=1, retain=True)
    gaps = [later - earlier for earlier, later in zip(timestamps, timestamps[1:])]
    gaps.append(sum(gaps) / len(gaps) if gaps else 0.1)  # pause after the last frame before the next round
    sent = 0
    while True:
        for grid, gap in zip(frames, gaps):
            client.publish(f"{base}/frame", frame_payload(grid), qos=0, retain=False)
            sent += 1
            sleep(gap / speed)
        if not loop:
            return sent


def main():
    parser = argparse.ArgumentParser(description="Replay the seat sample to MQTT as a demo mat")
    parser.add_argument("--chip-id", default="demo-take1")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed factor (default 1)")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True, help="repeat (default on)")
    parser.add_argument("--once", action="store_true", help="play the recording once and stop")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--user")
    parser.add_argument("--password")
    args = parser.parse_args()
    if args.speed <= 0:
        parser.error("--speed must be above 0")

    frames, timestamps = load_session(resource_path(SAMPLE), with_timestamps=True)
    if timestamps is None:
        sys.exit("The sample has no usable timestamps")
    settings = app_settings.effective_mqtt()
    host = args.host or settings["host"]
    port = args.port or settings["port"]
    user = args.user if args.user is not None else settings["username"]
    password = args.password if args.password is not None else settings["password"]

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"smartmat-demo-{args.chip_id}")
    if user:
        client.username_pw_set(user, password)
    client.will_set(f"smartmat/{args.chip_id}/status", "offline", qos=1, retain=True)
    client.connect(host, port)
    client.loop_start()
    print(f"Publishing {args.chip_id} to {host}:{port} (Ctrl+C to stop)")
    try:
        replay(client, args.chip_id, frames, timestamps, args.speed, args.loop and not args.once)
    except KeyboardInterrupt:
        pass
    finally:  # a clean disconnect does not fire the last will
        client.publish(f"smartmat/{args.chip_id}/status", "offline", qos=1, retain=True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
