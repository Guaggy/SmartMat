"""main.py: --help prints usage instead of opening the window; --server passes its other options on."""

import contextlib
import io
import unittest
from unittest import mock

import main


class MainArgsTests(unittest.TestCase):
    def test_help_prints_usage_and_does_not_open_the_app(self):
        out = io.StringIO()
        with mock.patch.dict("sys.modules", {"gui.desktop": None}), contextlib.redirect_stdout(out):  # importing it would fail
            self.assertEqual(main.main(["--help"]), 0)
            self.assertEqual(main.main(["-h"]), 0)
        self.assertIn("usage: main.py", out.getvalue())

    def test_server_options_are_handed_on(self):
        with mock.patch("server.__main__.main") as server_main:
            main.main(["--server", "--demo", "3", "--port", "8123"])
            server_main.assert_called_once_with(["--demo", "3", "--port", "8123"])
            server_main.reset_mock()
            main.main(["--server", "--help"])
            server_main.assert_called_once_with(["--help"])


if __name__ == "__main__":
    unittest.main()
