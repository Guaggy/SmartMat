"""A mat's passport store as the firmware keeps it (ESP32_China/src/mat_passport.h), in Python.

The same rules and the same message texts, so that the fake device (tools/fake_passport_device.py), the tests of the
server and the desktop, and the firmware's own host tests can all be checked against one set of test vectors. The
protocol is written down in ESP32_China/PASSPORT.md.

A device holds two slots of opaque bytes (processing.passport: MAGIC + zlib(JSON), at most MAX_BYTES) and a serial number.
Nothing here understands the content. Writing the factory slot, or the serial, needs the service key; the custom slot is
writable by anyone who can publish to the mat's topics (the broker login is the lock).
"""

import re

from processing import passport

SERIAL = re.compile(rb"[A-Za-z0-9_-]{1,24}")
ERRORS = ("slot", "empty", "too_big", "bad_magic", "locked", "serial", "storage")
KEY_HEADER = b"KEY:"


def _summary_slot(blob):
    return "null" if blob is None else f'{{"bytes":{len(blob)},"crc":"{passport.crc_hex(blob)}"}}'


def safe_name(text):
    """A name taken from a topic or payload, as it is echoed in a reply: letters, digits, _ and - only, 16 characters"""
    return re.sub(r"[^A-Za-z0-9_-]", "?", str(text))[:16]


def ack(op, slot, ok, err=None, blob=None):
    """The acknowledgement the device publishes on `passport/ack`; the same text the firmware builds with snprintf"""
    head = f'{{"op":"{op}","slot":"{safe_name(slot)}","ok":{"true" if ok else "false"}'
    if not ok:
        return head + f',"err":"{err}"}}'
    if blob is None:
        return head + "}"
    return head + f',"bytes":{len(blob)},"crc":"{passport.crc_hex(blob)}"}}'


def split_key(payload):
    """b"KEY:abc\\nrest" -> (b"abc", b"rest"); None when the payload has no key header"""
    if not payload.startswith(KEY_HEADER):
        return None
    end = payload.find(b"\n")
    if end < 0:
        return None
    return payload[len(KEY_HEADER):end], payload[end + 1:]


def _same_key(expected, got):
    """Constant-time compare; never true for a device without a service key"""
    if not expected:
        return False
    expected = expected.encode() if isinstance(expected, str) else expected
    difference = len(expected) ^ len(got)
    for index in range(max(len(expected), len(got))):
        difference |= (expected[index] if index < len(expected) else 0) ^ (got[index] if index < len(got) else 0)
    return difference == 0


class DeviceStore:
    def __init__(self, serial="", service_key="", slots=None):
        self.serial, self.service_key = serial, service_key
        self.slots = {"factory": None, "custom": None}
        self.slots.update(slots or {})

    def summary(self):
        """The retained message on `passport`: fixed key order, compact, exactly as the firmware prints it"""
        return (f'{{"serial":"{self.serial}","factory":{_summary_slot(self.slots["factory"])},'
                f'"custom":{_summary_slot(self.slots["custom"])},"max":{passport.MAX_BYTES}}}')

    def get(self, slot):
        """(bytes, None) or (None, ack text with the error): what `passport/get` answers on `passport/data/<slot>`"""
        if slot not in passport.SLOTS:
            return None, ack("get", str(slot)[:16], False, "slot")
        if self.slots[slot] is None:
            return None, ack("get", slot, False, "empty")
        return self.slots[slot], None

    def put(self, slot, payload):
        """`passport/put/<slot>`: the ack text. The slot is changed only when the ack says ok"""
        if slot not in passport.SLOTS:
            return ack("put", str(slot)[:16], False, "slot")
        blob = payload
        if slot == "factory":
            split = split_key(payload)
            if split is None or not _same_key(self.service_key, split[0]):
                return ack("put", slot, False, "locked")
            blob = split[1]
        if len(blob) == 0:
            return ack("put", slot, False, "empty")
        if len(blob) > passport.MAX_BYTES:
            return ack("put", slot, False, "too_big")
        if blob[:len(passport.MAGIC)] != passport.MAGIC:
            return ack("put", slot, False, "bad_magic")
        self.slots[slot] = bytes(blob)
        return ack("put", slot, True, blob=self.slots[slot])

    def clear(self, payload):
        """`passport/clear` with the slot name: only the custom slot can be cleared over MQTT"""
        if payload != b"custom":
            return ack("clear", payload[:16].decode("ascii", "replace"), False, "locked" if payload == b"factory" else "slot")
        self.slots["custom"] = None
        return ack("clear", "custom", True)

    def set_serial(self, payload):
        """`passport/serial`: `KEY:<service key>\\n<serial>`"""
        split = split_key(payload)
        if split is None or not _same_key(self.service_key, split[0]):
            return ack("serial", "", False, "locked")
        if not SERIAL.fullmatch(split[1]):
            return ack("serial", "", False, "serial")
        self.serial = split[1].decode("ascii")
        return ack("serial", "", True)
