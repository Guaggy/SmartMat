"""The desktop's side of the mat passport: look at a mat's slots, fetch a slot's calibration, save the current one to the
mat's custom slot, over the MQTT broker directly (no server needed, so it works for a single mat at a school too).

Pure logic over a PassportLink; gui/passport_panel.py is the thin window. Every function returns (ok, data_or_text) and
never raises, the way server_client does, with sentences written for the person at the desktop.
"""

import app_settings
from matlink.passport_link import PahoTransport, PassportError, PassportLink
from processing import passport


def connect(timeout=5.0):
    """A PassportLink on the broker from the app's MQTT settings; (True, link) or (False, text)"""
    settings = app_settings.effective_mqtt()
    try:
        transport = PahoTransport(settings["host"], settings["port"], settings["username"], settings["password"],
                                  "smartmat-desktop-passport")
    except Exception as error:   # paho missing or a bad address
        return False, f"cannot start MQTT: {error}"
    if not transport.wait_connected(timeout):
        transport.close()
        return False, f"cannot reach the MQTT broker at {settings['host']}:{settings['port']}"
    return True, PassportLink(transport, timeout)


def slot_lines(link, chip):
    """(True, [line, ...]) describing the mat's serial and both slots, or (False, text)"""
    summary = link.summary(chip)
    if summary is None:
        return False, "This mat has not told the broker about a passport (offline, or firmware without passport support)."
    lines = [f"Serial number: {summary.get('serial') or '(none)'}"]
    for slot in passport.SLOTS:
        if not summary.get(slot):
            lines.append(f"{slot.capitalize()}: empty")
            continue
        try:
            lines.append(f"{slot.capitalize()}: {passport.describe(link.read(chip, slot)[0])}")
        except PassportError as error:
            lines.append(f"{slot.capitalize()}: {error}")
    return True, lines


def fetch(link, chip, slot, shape):
    """(True, document) of a slot, if it is for a mat of this grid shape (rows, cols, either orientation)"""
    try:
        document, _blob = link.read(chip, slot)
    except PassportError as error:
        return False, str(error)
    if sorted(document["grid_shape"]) != sorted(shape):
        return False, f"That passport is for a {document['grid_shape'][0]}x{document['grid_shape'][1]} mat, this one is {shape[0]}x{shape[1]}."
    return True, document


def save_custom(link, chip, profile, by="", note="", analysis=None):
    """Write `profile` (a mat profile dict) to the custom slot as the next version. (True, {version, bytes}) or (False, text)"""
    summary = link.summary(chip) or {}
    version = 1
    try:
        version = passport.decode(link.read(chip, "custom")[1])["version"] + 1
    except PassportError:
        pass
    try:
        blob = passport.encode(passport.build("custom", summary.get("serial", ""), (profile or {}).get("model", ""), profile,
                                              analysis, version, by, note))
        ack = link.write(chip, "custom", blob)
    except (ValueError, PassportError) as error:
        return False, str(error)
    return True, {"version": version, "bytes": ack["bytes"]}
