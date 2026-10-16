"""Product name, company details and the shared colour palette."""

PRODUCT_NAME = "SmartMat"
COMPANY_NAME = "Verdian Medical"
VERSION = "0.1.0"
WEBSITE_URL = "https://www.verdianmedical.com"
CONTACT_EMAIL = "contact@verdianmedical.com"  # confirmed by the owner
DISCLAIMER = ("Not a medical device. SmartMat is an engineering aid: its metrics support investigating sustained "
              "loading, not a diagnosis or a validated risk score. Use alongside normal clinical assessment.")

# Shared design tokens: the desktop theme and the web UI (via /api/theme) both read these. Brand: navy #10182B, sage #5E9C83.
PALETTE_LIGHT = {
    "bg": "#E9EDF1", "panel": "#FFFFFF", "panel2": "#F4F6F8", "line": "#D3DAE2", "ink": "#10182B", "muted": "#586377",
    "accent": "#2F7A62", "accent_fill": "#5E9C83", "on_accent": "#FFFFFF", "brandbar": "#FFFFFF", "hm_bg": "#F1F4F7",
    "ok": "#2E7D5B", "warn": "#B7791F", "warn_text": "#8A5A00", "bad": "#A8231B", "idle": "#566074",
}
# brandbar (dark) is the navy behind assets/logo_lockup_dark.png, so the lockup sits on the bar without a seam
PALETTE_DARK = {
    "bg": "#0A101D", "panel": "#111A2D", "panel2": "#0D1525", "line": "#243049", "ink": "#E6EBF2", "muted": "#93A0B5",
    "accent": "#74B89C", "accent_fill": "#5E9C83", "on_accent": "#10182B", "brandbar": "#141824", "hm_bg": "#0A101D",
    "ok": "#6FC49C", "warn": "#E6B45A", "warn_text": "#E6B45A", "bad": "#F08A80", "idle": "#9AA6BA",
}
# Heatmap colour ramp: (t, (r, g, b)); cells below ~2 % of full scale fade into hm_bg.
HEATMAP_STOPS = [
    (0.0, (207, 230, 222)), (0.25, (126, 189, 168)), (0.5, (233, 196, 106)),
    (0.75, (224, 123, 57)), (0.9, (179, 38, 30)), (1.0, (107, 15, 26)),
]

ACCENT = PALETTE_LIGHT["accent"]      # buttons, links, active tab
DARK = PALETTE_LIGHT["ink"]           # text on light surfaces
MUTED = PALETTE_LIGHT["muted"]        # grey text
HEADER_BG = PALETTE_LIGHT["brandbar"]  # header strip
