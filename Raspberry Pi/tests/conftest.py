"""pytest only: keep tests from writing into the real user data folder."""

import sys

import pytest


@pytest.fixture(autouse=True)
def recordings_in_a_temp_folder(tmp_path, monkeypatch):
    """Tests that record (Recorder.save, the desktop's raw capture, ...) used to write into <app folder>/recordings
    and clean up after themselves; point every module's RECORDINGS_DIR at a temp folder instead.
    (With python -m unittest this does not apply: those tests still clean up after themselves.)"""
    import processing.recording as recording
    original = recording.RECORDINGS_DIR
    temp = tmp_path / "recordings"
    for module in list(sys.modules.values()):
        try:
            if getattr(module, "RECORDINGS_DIR", None) == original:
                monkeypatch.setattr(module, "RECORDINGS_DIR", temp)
        except Exception:  # lazy or odd modules: leave them alone
            continue
    yield
