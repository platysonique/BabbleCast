"""Tests for vertical mic meter and Bluetooth route availability helpers."""

from __future__ import annotations

from pathlib import Path

from babblecast.audio.android_routing import device_types_include_bluetooth


def test_device_types_include_bluetooth_a2dp(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.audio.android_routing.bluetooth_audio_type_ids",
        lambda: frozenset({8}),
    )
    assert device_types_include_bluetooth({8, 2})


def test_device_types_exclude_builtin_speaker_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.audio.android_routing.bluetooth_audio_type_ids",
        lambda: frozenset({8}),
    )
    assert not device_types_include_bluetooth({2})


def test_vertical_meter_fill_grows_from_bottom() -> None:
    source = (Path(__file__).resolve().parent.parent / "mobile" / "vertical_meter.py").read_text(
        encoding="utf-8"
    )
    assert "pos_y = iy + 1" in source
    assert "iy + th - fill_h" not in source
    assert "iy + int(th * self._peak)" in source
