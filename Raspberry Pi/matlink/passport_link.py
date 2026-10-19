"""Reading and writing a mat's passport over MQTT (the protocol is in ESP32_China/PASSPORT.md).

PassportLink talks to one broker through a small transport (publish / subscribe / a message handler) so the same code runs
over paho (PahoTransport, the real thing) and over LoopbackBus (tests, tools/fake_passport_device.py). Every call is a
request on `smartmat/<id>/passport/...` answered by the mat on `.../passport/ack` (or `.../passport/data/<slot>`), and
waits at most `timeout` seconds. Errors are PassportError with a sentence; nothing here understands the passport's content
(processing.passport does that).
"""

import json
import threading
import time

from processing import passport

PREFIX = "smartmat"
ACK_MESSAGES = {
    "locked": "the mat refused it: this needs the service key (or this slot is protected)",
    "slot": "the mat does not know that slot",
    "empty": "the mat has nothing to give or take here",
    "too_big": f"the passport is larger than the mat's slot ({passport.MAX_BYTES} bytes)",
    "bad_magic": "that is not a SmartMat passport",
    "serial": "serial numbers are 1-24 letters, digits, - or _",
    "storage": "the mat could not write its flash memory",
}


class PassportError(Exception):
    pass


class LoopbackBus:
    """An in-process broker with the transport interface: a message published reaches every subscriber of a matching
    topic (exact topics only, as the passport protocol uses) and retained messages reach late subscribers"""

    def __init__(self):
        self._lock = threading.RLock()
        self._handlers = []          # (transport, topic set)
        self.retained = {}

    def transport(self):
        return _LoopbackTransport(self)

    def _publish(self, sender, topic, payload, retain):
        with self._lock:
            if retain:
                self.retained[topic] = payload
            targets = [t for t in self._handlers if topic in t.topics]
        for target in targets:
            if target is not sender and target.handler is not None:
                target.handler(topic, payload)


class _LoopbackTransport:
    def __init__(self, bus):
        self.bus, self.topics, self.handler = bus, set(), None
        with bus._lock:
            bus._handlers.append(self)

    def subscribe(self, topic):
        self.topics.add(topic)
        retained = self.bus.retained.get(topic)
        if retained is not None and self.handler is not None:
            self.handler(topic, retained)

    def publish(self, topic, payload, retain=False):
        self.bus._publish(self, topic, payload, retain)

    def close(self):
        pass


class PahoTransport:
    """The same interface over a real broker"""

    def __init__(self, host, port=1883, username="", password="", client_id="smartmat-passport"):
        import paho.mqtt.client as mqtt
        self.handler = None
        self._topics = set()
        self._connected = threading.Event()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if username:
            self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_message = lambda _c, _u, msg: self.handler and self.handler(msg.topic, bytes(msg.payload))
        self._client.connect_async(host, port)
        self._client.loop_start()

    def _on_connect(self, client, *_):
        for topic in self._topics:
            client.subscribe(topic)
        self._connected.set()

    def wait_connected(self, timeout):
        return self._connected.wait(timeout)

    def subscribe(self, topic):
        self._topics.add(topic)
        if self._connected.is_set():
            self._client.subscribe(topic)

    def publish(self, topic, payload, retain=False):
        self._client.publish(topic, payload, retain=retain)

    def close(self):
        self._client.loop_stop()
        self._client.disconnect()


class PassportLink:
    def __init__(self, transport, timeout=5.0):
        self.transport, self.timeout = transport, timeout
        self._cond = threading.Condition()
        self._acks = {}        # chip id -> list of ack dicts not yet taken
        self._data = {}        # (chip id, slot) -> bytes
        self._summaries = {}   # chip id -> dict (retained summary)
        self._watching = set()
        self._request_lock = threading.Lock()   # one request at a time, so an ack is always the answer to the last request
        transport.handler = self._on_message

    # ---- incoming
    def _on_message(self, topic, payload):
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != PREFIX or parts[2] != "passport":
            return
        chip = parts[1]
        with self._cond:
            if len(parts) == 3:
                try:
                    self._summaries[chip] = json.loads(payload.decode("utf-8"))
                except ValueError:
                    return
            elif parts[3] == "ack" and len(parts) == 4:
                try:
                    self._acks.setdefault(chip, []).append(json.loads(payload.decode("utf-8")))
                except ValueError:
                    return
            elif parts[3] == "data" and len(parts) == 5:
                self._data[(chip, parts[4])] = bytes(payload)
            else:
                return
            self._cond.notify_all()

    def _watch(self, chip):
        if chip not in self._watching:
            self._watching.add(chip)
            base = f"{PREFIX}/{chip}/passport"
            for topic in (base, f"{base}/ack", f"{base}/data/factory", f"{base}/data/custom"):
                self.transport.subscribe(topic)

    def _wait(self, predicate):
        deadline = time.monotonic() + self.timeout
        with self._cond:
            while True:
                found = predicate()
                if found is not None:
                    return found
                left = deadline - time.monotonic()
                if left <= 0:
                    raise PassportError("the mat did not answer (is it online and on this broker?)")
                self._cond.wait(left)

    def _command(self, chip, op, topic_tail, payload, slot=""):
        """Publish a command and return its ack; a refusal is a PassportError"""
        with self._request_lock:
            self._watch(chip)
            with self._cond:
                self._acks[chip] = []
                if op == "get":
                    self._data.pop((chip, slot), None)
            self.transport.publish(f"{PREFIX}/{chip}/passport/{topic_tail}", payload)

            def answered():
                for ack in self._acks.get(chip, []):
                    if ack.get("op") == op:
                        return ack
                if op == "get" and (chip, slot) in self._data:
                    return {"op": "get", "ok": True}
                return None

            ack = self._wait(answered)
        if not ack.get("ok"):
            error = ack.get("err", "")
            raise PassportError(ACK_MESSAGES.get(error, f"the mat refused it ({error or 'no reason given'})"))
        return ack

    # ---- calls
    def summary(self, chip, wait=True):
        """The mat's retained summary {serial, factory, custom, max}; None if it never published one"""
        self._watch(chip)
        try:
            return self._wait(lambda: self._summaries.get(chip)) if wait else self._summaries.get(chip)
        except PassportError:
            return None

    def read(self, chip, slot):
        """(document, blob) of a slot; PassportError if empty, unreachable, or the bytes are not a passport"""
        self._command(chip, "get", "get", slot.encode(), slot)
        with self._cond:
            blob = self._data[(chip, slot)]
        try:
            return passport.decode(blob), blob
        except ValueError as error:
            raise PassportError(str(error)) from error

    def write(self, chip, slot, blob, service_key=""):
        """Store a passport's bytes; verifies the mat's CRC against ours. The factory slot needs the service key."""
        if slot not in passport.SLOTS:
            raise PassportError("slot must be factory or custom")
        payload = blob
        if slot == "factory":
            payload = b"KEY:" + service_key.encode() + b"\n" + blob
        ack = self._command(chip, "put", f"put/{slot}", payload, slot)
        if ack.get("bytes") != len(blob) or ack.get("crc") != passport.crc_hex(blob):
            raise PassportError("the mat stored something different from what was sent")
        return ack

    def clear_custom(self, chip):
        self._command(chip, "clear", "clear", b"custom", "custom")

    def set_serial(self, chip, serial, service_key):
        self._command(chip, "serial", "serial", b"KEY:" + service_key.encode() + b"\n" + serial.encode())

    def close(self):
        self.transport.close()
