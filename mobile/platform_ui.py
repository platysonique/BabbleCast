"""Platform helpers for mobile UI branching."""

from __future__ import annotations


def is_android() -> bool:
    try:
        from kivy.utils import platform

        return platform == "android"
    except Exception:
        return False
