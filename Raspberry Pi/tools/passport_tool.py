"""Read and write the passport kept on a mat (ESP32_China/PASSPORT.md) from the command line, over the MQTT broker.

    python tools/passport_tool.py show      <chip-id>
    python tools/passport_tool.py save      <chip-id> custom   FILE.json     # a passport document (or a mat profile) -> slot
    python tools/passport_tool.py fetch     <chip-id> custom   OUT.smp       # the slot's bytes -> file (a backup)
    python tools/passport_tool.py restore   <chip-id> custom   IN.smp        # bytes from fetch -> slot
    python tools/passport_tool.py clear     <chip-id>                        # empties the custom slot
    python tools/passport_tool.py factory   <chip-id> FILE.json --service-key KEY [--serial SM-0001]
    python tools/passport_tool.py serial    <chip-id> SM-0001 --service-key KEY

`save` and `factory` take either a passport document (smartmat_mat_passport_v1) or a mat profile
(smartmat_mat_profile_v1, as saved by the desktop app or the server's profiles folder), which is wrapped in one.
The factory slot and the serial number need the mat's service key (secrets.h on the board).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app_settings
from passport_link import PahoTransport, PassportError, PassportLink
from processing import passport


def document_from(path, slot, serial, by, note):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") == passport.PROFILE_FORMAT:
        return passport.build(slot, serial or "", data.get("model", ""), data, None, 1, by, note)
    document = dict(data, slot=slot)
    if serial:
        document["serial"] = serial
    passport.decode(passport.MAGIC + __import__("zlib").compress(passport.canonical(document)))   # checked like a device read
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("show", "save", "fetch", "restore", "clear", "factory", "serial"))
    parser.add_argument("chip_id")
    parser.add_argument("rest", nargs="*")
    parser.add_argument("--service-key", default="")
    parser.add_argument("--serial", default="")
    parser.add_argument("--by", default="passport_tool")
    parser.add_argument("--note", default="")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    mqtt = app_settings.effective_mqtt()
    transport = PahoTransport(args.host or mqtt["host"], args.port or mqtt["port"], args.user or mqtt["username"],
                              args.password if args.password is not None else mqtt["password"], "smartmat-passport-tool")
    if not transport.wait_connected(args.timeout):
        print("could not reach the MQTT broker", file=sys.stderr)
        return 2
    link = PassportLink(transport, args.timeout)
    chip, rest = args.chip_id, args.rest
    try:
        if args.command == "show":
            summary = link.summary(chip)
            if summary is None:
                raise PassportError("the mat has not published a passport summary (offline or older firmware)")
            print(f"serial {summary['serial'] or '(none)'}")
            for slot in passport.SLOTS:
                entry = summary[slot]
                if entry is None:
                    print(f"{slot}: empty")
                    continue
                try:
                    print(f"{slot}: {passport.describe(link.read(chip, slot)[0])} [{entry['bytes']} bytes, crc {entry['crc']}]")
                except PassportError as error:
                    print(f"{slot}: {entry['bytes']} bytes, crc {entry['crc']} - {error}")
        elif args.command in ("save", "factory"):
            slot = "factory" if args.command == "factory" else rest[0]
            path = rest[0] if args.command == "factory" else rest[1]
            document = document_from(path, slot, args.serial, args.by, args.note)
            link.write(chip, slot, passport.encode(document), args.service_key)
            print(f"{slot} written")
        elif args.command == "fetch":
            _document, blob = link.read(chip, rest[0])
            Path(rest[1]).write_bytes(blob)
            print(f"{len(blob)} bytes saved to {rest[1]}")
        elif args.command == "restore":
            blob = Path(rest[1]).read_bytes()
            passport.decode(blob)
            link.write(chip, rest[0], blob, args.service_key)
            print(f"{rest[0]} restored")
        elif args.command == "clear":
            link.clear_custom(chip)
            print("custom slot cleared")
        elif args.command == "serial":
            link.set_serial(chip, rest[0], args.service_key)
            print("serial set")
    except (PassportError, ValueError, IndexError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
