"""ADB-driven connect smoke — only when activity extra bbc_smoke_connect is set."""

from __future__ import annotations

import logging
import re

from babblecast.constants import DEFAULT_WS_PORT

logger = logging.getLogger(__name__)

_SMOKE_EXTRA = "bbc_smoke_connect"
_HOST_PORT = re.compile(
    r"^(?P<host>(?:\d{1,3}(?:\.\d{1,3}){3}|[\w.-]+)):(?P<port>\d{1,5})$"
)


def parse_smoke_connect(value: str | None) -> tuple[str, int] | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    match = _HOST_PORT.match(text)
    if not match:
        return None
    host = match.group("host")
    port = int(match.group("port"))
    if port < 1 or port > 65535:
        return None
    return host, port


def read_smoke_connect_target() -> tuple[str, int] | None:
    try:
        from kivy.utils import platform

        if platform != "android":
            return None
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return None
        intent = activity.getIntent()
        if intent is None:
            return None
        extra = intent.getStringExtra(_SMOKE_EXTRA)
        parsed = parse_smoke_connect(extra)
        if parsed:
            logger.info("Smoke connect intent: %s:%s", parsed[0], parsed[1])
        return parsed
    except Exception:
        logger.debug("Smoke connect intent read failed", exc_info=True)
        return None
