"""Builds the app icons from the repo's logo sheet (Raspberry Pi/branding_source/Logo.jpg).
Run: python3 scripts/make-icons.py   (needs Pillow). The sheet is only 604 px per tile, so the 1024 px icon is
upscaled; replace assets/ with vector-exported PNGs when the brand files exist."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT.parent / "Raspberry Pi" / "branding_source" / "Logo.jpg"
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)

tile = Image.open(SHEET).convert("RGB").crop((4, 4, 604, 604))  # dark tile with the mark
bg = tile.getpixel((20, 20))
print("background colour", "#%02X%02X%02X" % bg)

def mark_alpha(img, white=False):
    """Pixels that differ from the background become the mark; returns RGBA on transparent"""
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    src, dst = img.load(), out.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = src[x, y]
            d = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            a = max(0, min(255, (d - 25) * 4))
            dst[x, y] = (255, 255, 255, a) if white else (r, g, b, a)
    return out

big = tile.resize((1024, 1024), Image.LANCZOS)
big.save(OUT / "icon.png")  # iOS: square, opaque

mark = mark_alpha(big)
def centred(img, size):
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    scaled = img.resize((size, size), Image.LANCZOS)
    canvas.paste(scaled, ((1024 - size) // 2,) * 2, scaled)
    return canvas

centred(mark, 680).save(OUT / "android-icon-foreground.png")           # inside the adaptive safe zone
centred(mark_alpha(big, white=True), 680).save(OUT / "android-icon-monochrome.png")
Image.new("RGB", (1024, 1024), bg).save(OUT / "android-icon-background.png")
centred(mark, 900).save(OUT / "splash-icon.png")
mark.resize((48, 48), Image.LANCZOS).save(OUT / "favicon.png")
centred(mark_alpha(big, white=True), 900).resize((96, 96), Image.LANCZOS).save(OUT / "notification-icon.png")  # Android status bar: white on transparent
