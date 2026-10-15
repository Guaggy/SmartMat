"""DesktopApp.restart_discovery must not block the GUI thread on the old source's slow stop()."""

import threading
import time
import unittest
from types import SimpleNamespace

from gui.desktop import DesktopApp


class SlowStopSource:
    def __init__(self):
        self.stopped = threading.Event()
        self.mats, self.status, self.error = {"old": {}}, {}, None

    def stop(self):
        time.sleep(1.0)
        self.stopped.set()


class RestartDiscoveryTest(unittest.TestCase):
    def test_slow_stop_does_not_block_and_old_source_is_dropped(self):
        old = SlowStopSource()
        status = SimpleNamespace(value="", get=lambda: status.value, set=lambda v: setattr(status, "value", v))
        refreshed = []
        app = SimpleNamespace(_discovery=old, status_var=status, _discovery_error=None, _mats={"old": {}},
                              _status={}, _publish_web=lambda force: None,
                              _refresh_devices=lambda: refreshed.append(app._discovery))
        start = time.monotonic()
        DesktopApp.restart_discovery(app)
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertIsNone(app._discovery)  # the old source no longer feeds the device list
        self.assertEqual((app._mats, refreshed), ({}, [None]))  # new listener is built by _refresh_devices
        self.assertTrue(old.stopped.wait(5))  # and it is still stopped, in the background


if __name__ == "__main__":
    unittest.main()
