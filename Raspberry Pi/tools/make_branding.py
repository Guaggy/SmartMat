"""Cut the logo sheet (branding_source/Logo.jpg) into the app assets. Run from 'Raspberry Pi': python tools/make_branding.py"""
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "branding_source" / "Logo.jpg"
OUT = ROOT / "assets"
NAVY = (0x10, 0x18, 0x2B)
PAD = 12
MARK_W, LOCKUP_W = 160, 520
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
# name -> (box on the sheet, target width)
CELLS = {
    "logo_mark_dark": ((8, 8, 600, 600), MARK_W),
    "logo_mark_light": ((616, 8, 1208, 600), MARK_W),
    "logo_lockup_dark": ((8, 616, 1208, 862), LOCKUP_W),
    "logo_lockup_light": ((8, 880, 1208, 1126), LOCKUP_W),
}


def content(cell, tol=48):
    """Crop to what differs from the corner background (tol absorbs JPEG noise), plus PAD of that background."""
    cell = cell.convert("RGB")
    bg = cell.getpixel((0, 0))
    diff = ImageChops.difference(cell, Image.new("RGB", cell.size, bg)).convert("L").point(lambda v: 255 if v > tol else 0)
    x0, y0, x1, y1 = diff.getbbox()
    canvas = Image.new("RGB", (x1 - x0 + 2 * PAD, y1 - y0 + 2 * PAD), bg)
    canvas.paste(cell.crop((x0, y0, x1, y1)), (PAD, PAD))
    return canvas


def scaled(img, width):
    return img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)


def main():
    sheet = Image.open(SHEET)
    OUT.mkdir(exist_ok=True)
    for name, (box, width) in CELLS.items():
        scaled(content(sheet.crop(box)), width).save(OUT / f"{name}.png")
    # app icon: the navy mark at ~76 % of the width, centred on a navy square tile
    size = 256
    mark = scaled(content(sheet.crop(CELLS["logo_mark_dark"][0])), round(size * 0.76))
    tile = Image.new("RGB", (size, size), NAVY)
    tile.paste(mark, ((size - mark.width) // 2, (size - mark.height) // 2))
    tile.save(OUT / "icon_256.png")
    tile.save(OUT / "icon.ico", sizes=[(s, s) for s in ICON_SIZES])


if __name__ == "__main__":
    main()
