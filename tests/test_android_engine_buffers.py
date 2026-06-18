"""Document pyjnius byte[] copy contract (regression guard for silent mic/speaker)."""

from __future__ import annotations

from pathlib import Path


def test_android_engine_uses_java_byte_array_copy_helpers() -> None:
    """cast('byte[]', bytearray) does not sync AudioRecord reads back to Python."""
    text = Path(__file__).resolve().parents[1].joinpath("babblecast/audio/android_engine.py").read_text(
        encoding="utf-8"
    )
    assert "_java_byte_array" in text
    assert "_copy_java_to_python" in text
    assert "_copy_python_to_java" in text
    assert "cast(\"byte[]\"" not in text
