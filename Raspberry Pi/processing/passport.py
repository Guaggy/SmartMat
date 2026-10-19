"""The mat "passport": the calibration that belongs to one mat, kept on the mat's own ESP32 so it travels with the mat.

A passport has two slots: `factory` (written at the factory, protected by a service key on the device) and `custom`
(written by whoever calibrates the mat for a site, e.g. from the desktop app or the server; a backup too). A slot holds one
document with the mat's calibration profile (tare, pressure calibration, orientation, size, ROI), its serial number and
model, a version, who wrote it and when, and optionally the analysis settings that belong to the mat (flat keys of the
server's layered settings: the engineering preset and the risk indices).

Only device-bound data goes in: names, rooms, alert thresholds and users stay at the site.

On the device a slot is opaque bytes: MAGIC + zlib(canonical JSON), at most MAX_BYTES, with a CRC-32 of exactly those bytes.
The firmware never parses JSON (ESP32_China/PASSPORT.md has the MQTT protocol); everything that understands the content is
here. Pure functions, no I/O.
"""

import json
import time
import zlib

FORMAT = "smartmat_mat_passport_v1"
PROFILE_FORMAT = "smartmat_mat_profile_v1"   # processing.calibration.PROFILE_FORMAT, repeated to keep this module free of numpy
MAGIC = b"SMP1"
SLOTS = ("factory", "custom")
MAX_BYTES = 16384   # per slot, compressed; the firmware refuses more (and its MQTT buffer is sized for it)
KEEP_KEYS = ("profile", "analysis")


def crc32(data):
    """CRC-32 (IEEE, as zlib.crc32 and the firmware compute it) of bytes"""
    return zlib.crc32(data) & 0xFFFFFFFF


def crc_hex(data):
    return f"{crc32(data):08x}"


def canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build(slot, serial, model, profile, analysis=None, version=1, by="", note="", t=None):
    """A passport document. `profile` is a mat profile dict (processing.calibration), `analysis` a flat {key: value} of
    the mat's own analysis overrides or None. ValueError for anything that could not be read back."""
    if slot not in SLOTS:
        raise ValueError(f"slot must be one of {', '.join(SLOTS)}")
    if not isinstance(profile, dict) or profile.get("format") != PROFILE_FORMAT:
        raise ValueError(f"profile must be a {PROFILE_FORMAT} object")
    shape = profile.get("grid_shape")
    if not (isinstance(shape, list) and len(shape) == 2 and all(isinstance(side, int) and side >= 1 for side in shape)):
        raise ValueError("the profile has no valid grid_shape")
    if analysis is not None and not (isinstance(analysis, dict) and all(isinstance(key, str) for key in analysis)):
        raise ValueError("analysis must be a flat {key: value} object or None")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("version must be a whole number from 1")
    return {"format": FORMAT, "slot": slot, "serial": str(serial or ""), "model": str(model or ""), "grid_shape": list(shape),
            "version": version, "written_at": float(time.time() if t is None else t), "written_by": str(by or ""),
            "note": str(note or ""), "profile": profile, "analysis": analysis}


def encode(document):
    """The bytes the device stores for a document. ValueError when they would not fit a slot"""
    blob = MAGIC + zlib.compress(canonical(document), 9)
    if len(blob) > MAX_BYTES:
        raise ValueError(f"the passport is {len(blob)} bytes, a slot holds {MAX_BYTES}")
    return blob


def decode(blob):
    """The document in a slot's bytes, checked. ValueError with a sentence for anything that is not a passport"""
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < len(MAGIC) + 2:
        raise ValueError("empty or too short to be a passport")
    blob = bytes(blob)
    if blob[:len(MAGIC)] != MAGIC:
        raise ValueError("not a SmartMat passport (wrong start bytes)")
    if len(blob) > MAX_BYTES:
        raise ValueError("larger than a passport slot")
    try:
        document = json.loads(zlib.decompress(blob[len(MAGIC):]).decode("utf-8"))
    except (zlib.error, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"the passport is damaged: {error}") from error
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise ValueError(f"not a {FORMAT} document")
    for key in ("slot", "serial", "model", "grid_shape", "version", "profile"):
        if key not in document:
            raise ValueError(f"the passport has no {key}")
    if document["slot"] not in SLOTS:
        raise ValueError("the passport names an unknown slot")
    build(document["slot"], document["serial"], document["model"], document["profile"], document.get("analysis"),
          document["version"])   # the same checks as when writing one
    return document


def describe(document):
    """A short line for people: 'custom v3 by Admin, 2026-10-19 12:01 (soft cushion)' """
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(document.get("written_at", 0)))
    by = f" by {document['written_by']}" if document.get("written_by") else ""
    note = f" ({document['note']})" if document.get("note") else ""
    return f"{document['slot']} v{document['version']}{by}, {when}{note}"


def keep(document):
    """The part of a document that is the mat's calibration (what is compared and adopted): profile and analysis"""
    return {key: document.get(key) for key in KEEP_KEYS}
