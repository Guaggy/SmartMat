"""The dashboard's static files hang together (no browser): history.js is served and loaded before app.js, and every element
id the scripts look up with $("...") exists in index.html or is built by the script itself."""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from server.alerts import AlertManager
from server.app import create_app
from server.store import Store

STATIC = Path(__file__).resolve().parent.parent / "server" / "static"


class StaticFiles(unittest.TestCase):
    def test_history_script_is_served_and_loaded_before_the_app(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        store = Store(folder / "smartmat.db")
        self.addCleanup(store.close)
        client = create_app(store, AlertManager(), {}).test_client()
        reply = client.get("/history.js")
        self.assertEqual(reply.status_code, 200)
        reply.close()
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertLess(page.index('src="history.js"'), page.index('src="app.js"'))

    def test_every_looked_up_id_exists_in_the_page(self):
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        ids = set(re.findall(r'id="([^"]+)"', page))
        built = {"settings", "matcfg", "help", "dash"}   # page sections are in the html; none are made by script
        for name in ("history.js", "app.js"):
            source = (STATIC / name).read_text(encoding="utf-8")
            missing = {i for i in re.findall(r'\$\("([A-Za-z0-9_]+)"\)', source)} - ids - built
            self.assertEqual(missing, set(), name)


if __name__ == "__main__":
    unittest.main()
