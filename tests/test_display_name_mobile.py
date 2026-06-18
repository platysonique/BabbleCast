"""Tests for mobile display name defaults."""

from __future__ import annotations

from babblecast.config import UserSettings


def test_default_display_name_uses_settings() -> None:
    settings = UserSettings(display_name="Studio A")
    from mobile.display_name import default_display_name

    assert default_display_name(settings) == "Studio A"


def test_default_display_name_android_skips_gethostname(monkeypatch) -> None:
    monkeypatch.setattr("mobile.display_name.platform_name", lambda: "android")

    def _boom() -> str:
        raise OSError("gethostname should not run on Android")

    monkeypatch.setattr("socket.gethostname", _boom)
    from mobile.display_name import default_display_name

    assert default_display_name(UserSettings()) == "Guest"
