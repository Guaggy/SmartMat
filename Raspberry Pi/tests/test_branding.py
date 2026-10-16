import importlib.util
import re
import unittest
from pathlib import Path

from PIL import Image

import branding
from paths import resource_path

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class BrandingTests(unittest.TestCase):
    def test_assets_exist(self):
        for name in ("logo_mark_light.png", "logo_mark_dark.png", "logo_lockup_light.png", "logo_lockup_dark.png",
                     "icon_256.png", "icon.ico"):
            self.assertTrue(resource_path("assets/" + name).is_file(), name)

    def test_ico_sizes(self):
        sizes = Image.open(resource_path("assets/icon.ico")).ico.sizes()
        self.assertEqual(sizes, {(s, s) for s in (16, 24, 32, 48, 64, 128, 256)})

    def test_palettes(self):
        self.assertEqual(branding.PALETTE_LIGHT.keys(), branding.PALETTE_DARK.keys())
        for palette in (branding.PALETTE_LIGHT, branding.PALETTE_DARK):
            for key, value in palette.items():
                self.assertRegex(value, HEX, key)
        self.assertEqual(branding.ACCENT, branding.PALETTE_LIGHT["accent"])
        stops = [t for t, _ in branding.HEATMAP_STOPS]
        self.assertEqual(stops, sorted(stops))
        self.assertTrue(all(len(rgb) == 3 and all(0 <= c <= 255 for c in rgb) for _, rgb in branding.HEATMAP_STOPS))

    def test_example_config_starts_in_easy_mode(self):
        path = Path(__file__).resolve().parent.parent / "config.example.py"
        spec = importlib.util.spec_from_file_location("config_example", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.START_IN_SIMPLE_MODE)


if __name__ == "__main__":
    unittest.main()
