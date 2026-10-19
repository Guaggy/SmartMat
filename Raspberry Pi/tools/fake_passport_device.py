"""A stand-in for a mat's passport service on a real broker: answers like the firmware (ESP32_China/PASSPORT.md) so the
server, the desktop and tools/passport_tool.py can be tried without a board. Pair it with tools/publish_demo_mat.py (same
--chip-id) to get a whole mat. Flash memory is a dict: it starts as given and is forgotten when this exits.

    python tools/fake_passport_device.py --chip-id demo-take1 --serial SM-0001 --service-key secret --custom 20x20
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app_settings
from passport_fake import FakePassportDevice
from passport_link import PahoTransport
from processing import passport


def demo_blob(slot, shape, serial, note):
    from server.__main__ import demo_profile
    rows, cols = (int(part) for part in shape.lower().split("x"))
    return passport.encode(passport.build(slot, serial, "MC266", demo_profile(rows, cols), None, 1, "fake device", note))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chip-id", required=True)
    parser.add_argument("--serial", default="")
    parser.add_argument("--service-key", default="")
    parser.add_argument("--factory", metavar="ROWSxCOLS", help="start with a factory passport for a mat of this size")
    parser.add_argument("--custom", metavar="ROWSxCOLS", help="start with a custom passport for a mat of this size")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--user")
    parser.add_argument("--password")
    args = parser.parse_args(argv)
    mqtt = app_settings.effective_mqtt()
    transport = PahoTransport(args.host or mqtt["host"], args.port or mqtt["port"], args.user or mqtt["username"],
                              args.password if args.password is not None else mqtt["password"], f"fake-passport-{args.chip_id}")
    slots = {}
    for slot, shape in (("factory", args.factory), ("custom", args.custom)):
        if shape:
            slots[slot] = demo_blob(slot, shape, args.serial, "fake")
    transport.wait_connected(10)
    FakePassportDevice(transport, args.chip_id, args.serial, args.service_key, slots)
    print(f"fake passport service for {args.chip_id} is up (Ctrl+C to stop)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        transport.close()


if __name__ == "__main__":
    main()
