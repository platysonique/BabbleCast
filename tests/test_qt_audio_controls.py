"""Source checks for compressed Qt self-audio controls layout."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_detail_drawer_uses_three_column_audio_row() -> None:
    source = (ROOT / "babblecast" / "client" / "qt" / "detail_drawer.py").read_text(
        encoding="utf-8"
    )
    assert "audio_row = QHBoxLayout()" in source
    assert "VolumeKnob" in source
    assert "compact=True" in source
    assert "_master_slider" not in source


def test_volume_knob_is_custom_radial_dial() -> None:
    source = (ROOT / "babblecast" / "client" / "qt" / "volume_knob.py").read_text(
        encoding="utf-8"
    )
    assert "_RadialDial" in source
    assert 'QColor("#ffffff")' in source
    assert "setRange(0, 200)" not in source
