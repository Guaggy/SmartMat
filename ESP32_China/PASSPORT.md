# Mat passport (MQTT protocol)

The passport is the calibration that belongs to *this* mat, kept in the ESP32's flash so it travels with the mat:
write it before shipping, read it back as a backup, and a new mat that shows up at a server can be calibrated
without anyone touching it.

The firmware never parses it. A slot is an opaque blob of at most 16384 bytes that starts with `SMP1`
(`SMP1` + zlib(JSON), made by `Raspberry Pi/processing/passport.py`); the board checks the start bytes and the size,
stores the bytes and reports their CRC-32. Rules live in `src/mat_passport.h` (host test:
`pio test -e native -f test_passport`); its Python twin is `Raspberry Pi/passport_device.py`, and both are tested
against the same message texts.

Only device-bound data goes in (calibration profile, size, model, optional analysis overrides). Names, rooms,
alert thresholds and users stay at the site.

## Slots

| slot | who may write | cleared over MQTT |
|---|---|---|
| `factory` | payload must start with `KEY:<service key>\n` | never |
| `custom` | anyone logged in to the broker | yes |

The service key is `passport_service_key` in `src/secrets.h`. Empty = the factory slot and the serial are read-only
on that board. The broker login is the lock for `custom`; use a broker with passwords (and TLS on untrusted networks).

## Topics (`smartmat/<chip_id>/passport...`)

Board subscribes (exact topics, not a wildcard):

| topic | payload | answer |
|---|---|---|
| `passport/get` | slot name | bytes on `passport/data/<slot>` (not retained), or an error ack |
| `passport/put/<slot>` | blob (factory: `KEY:<key>\n` + blob) | ack with `bytes` and `crc` of what was stored |
| `passport/clear` | `custom` | ack |
| `passport/serial` | `KEY:<key>\n<serial>` | ack |

Board publishes:

* `passport` (retained): `{"serial":"SM-0001","factory":null,"custom":{"bytes":812,"crc":"0bfc9cf7"},"max":16384}`,
  on connect and after every change.
* `passport/ack`: `{"op":"put","slot":"custom","ok":true,"bytes":812,"crc":"0bfc9cf7"}` or
  `{"op":"put","slot":"factory","ok":false,"err":"locked"}`. Errors: `slot`, `empty`, `too_big`, `bad_magic`,
  `locked`, `serial`, `storage`. Echoed names are sanitised (letters, digits, `_`, `-`; 16 characters).
* `passport/data/<slot>`: the stored bytes.

A write is stored to a temporary file and renamed, so a power cut leaves the old slot whole. Serial numbers are
1-24 letters, digits, `-` or `_`; the MQTT identity stays the chip id.

## Who talks to it

* `Raspberry Pi/passport_link.py`: client (verifies the CRC the board reports against the bytes sent).
* Server: `GET /api/mats/<id>/passport`, `POST .../passport/adopt` and `.../passport/write` (admin PIN); a mat with no
  saved calibration takes its passport on first contact (custom before factory), logged as `passport adopted`.
* `Raspberry Pi/tools/passport_tool.py`: command line for show / save / fetch / restore / clear / factory / serial.
* `Raspberry Pi/tools/fake_passport_device.py`: the board's behaviour in Python, for trying all this without hardware.

Both boards carry it: `ESP32_China` and `ESP32_Resistive` have identical copies of `src/mat_passport.h` and `src/passport_service.h` (a Python test fails if they drift).

## Not tested on hardware yet

The Arduino glue in `main.cpp` (LittleFS, PubSubClient callback, 16 KB buffer) is only syntax-checked against stub
headers; the full firmware build could not run here. Flash the `esp32-s3-simulate` env and run
`python tools/passport_tool.py show <chip-id>` against it.
