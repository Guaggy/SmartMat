"""A mat's passport service in Python: the firmware's MQTT behaviour (ESP32_China/src/main.cpp) on top of DeviceStore, for
tests and for trying the server and the desktop without a board (tools/fake_passport_device.py). Same topics and messages."""

from passport_device import DeviceStore, ack
from passport_link import PREFIX


class FakePassportDevice:
    def __init__(self, transport, chip_id, serial="", service_key="", slots=None):
        self.transport, self.chip, self.store = transport, chip_id, DeviceStore(serial, service_key, slots)
        self.base = f"{PREFIX}/{chip_id}/passport"
        transport.handler = self._on_message
        for tail in ("get", "clear", "serial", "put/factory", "put/custom"):
            transport.subscribe(f"{self.base}/{tail}")
        self.publish_summary()

    def publish_summary(self):
        self.transport.publish(self.base, self.store.summary().encode(), retain=True)

    def _ack(self, text):
        self.transport.publish(f"{self.base}/ack", text.encode())

    def _on_message(self, topic, payload):
        tail = topic[len(self.base) + 1:]
        if tail == "get":
            slot = payload.decode("ascii", "replace")
            blob, error = self.store.get(slot)
            if error:
                self._ack(error)
            else:
                self.transport.publish(f"{self.base}/data/{slot}", blob)
        elif tail == "clear":
            self._ack(self.store.clear(payload))
            self.publish_summary()
        elif tail == "serial":
            self._ack(self.store.set_serial(payload))
            self.publish_summary()
        elif tail.startswith("put/"):
            self._ack(self.store.put(tail[4:], payload))
            self.publish_summary()
