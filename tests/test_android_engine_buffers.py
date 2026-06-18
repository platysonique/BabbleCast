"""Regression guards for pyjnius PCM buffers on Android."""

from __future__ import annotations

from pathlib import Path


def test_android_engine_uses_java_short_arrays_not_byte() -> None:
    """Primitive arrays must use jarray/reflect — autoclass('[S') has no constructor."""
    text = Path(__file__).resolve().parents[1].joinpath("babblecast/audio/android_engine.py").read_text(
        encoding="utf-8"
    )
    assert "jarray" in text
    assert "_java_short_array" in text
    assert 'autoclass("[S")' not in text
    assert "autoclass('[S')" not in text
    assert "_java_byte_array" not in text
    assert 'cast("byte[]"' not in text


def test_bridge_android_audio_finish_is_zero_arg() -> None:
    """Kivy Clock passes _dt; _defer_main_thread calls fn() with no args."""
    text = Path(__file__).resolve().parents[1].joinpath("babblecast/client/bridge.py").read_text(encoding="utf-8")
    assert "def _finish() -> None:" in text
    assert "_defer_main_thread(0, _finish)" in text
