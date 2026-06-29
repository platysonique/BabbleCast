"""Safe default display names for mobile — avoid blocking DNS on Android."""

from __future__ import annotations

import socket

from babblecast.audio.factory import platform_name
from babblecast.config import UserSettings


def default_display_name(settings: UserSettings | None = None) -> str:
    if settings and settings.display_name:
        return settings.display_name.strip()
    if platform_name() == "android":
        return "Guest"
    try:
        name = socket.gethostname().strip()
        return name or "Guest"
    except Exception:
        return "Guest"
