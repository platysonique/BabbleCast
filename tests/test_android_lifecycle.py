"""Tests for Android lifecycle helpers."""

from __future__ import annotations

from mobile.android_lifecycle import should_run_in_background


def test_should_run_in_background_when_voice_active() -> None:
    assert should_run_in_background(True) is True
    assert should_run_in_background(False) is False
