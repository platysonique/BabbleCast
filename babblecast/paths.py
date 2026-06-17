"""Writable app data locations (desktop + Android)."""

from __future__ import annotations

import os
from pathlib import Path


def app_config_dir(*, create: bool = False) -> Path:
    """
    Directory for BabbleCast settings and local data.

    Desktop: ~/.config/babblecast (or XDG_CONFIG_HOME).
    Android: app-private storage (never /data/.config).
    """
    android_private = os.environ.get("ANDROID_PRIVATE")
    if android_private:
        path = Path(android_private) / "babblecast"
    else:
        try:
            from kivy.utils import platform as kivy_platform

            if kivy_platform == "android":
                from android.storage import app_storage_path

                path = Path(app_storage_path()) / "babblecast"
            else:
                raise ImportError
        except ImportError:
            base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
            path = Path(base) / "babblecast"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
