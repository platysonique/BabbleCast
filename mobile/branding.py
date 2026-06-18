"""Shared BabbleCast branding widgets for mobile."""

from __future__ import annotations

from pathlib import Path

from kivy.metrics import dp
from kivy.uix.image import Image


def asset_path(name: str) -> str:
    """Resolve a file under project ``assets/`` (desktop + Android bundle)."""
    root = Path(__file__).resolve().parent.parent
    path = root / "assets" / name
    if path.is_file():
        return str(path)
    return f"assets/{name}"


def banner_widget(*, height_dp: float = 72) -> Image:
    """Horizontal logo banner (``assets/splash.png``)."""
    return Image(
        source=asset_path("splash.png"),
        size_hint=(1, None),
        height=dp(height_dp),
        fit_mode="contain",
        allow_stretch=True,
        keep_ratio=True,
    )
