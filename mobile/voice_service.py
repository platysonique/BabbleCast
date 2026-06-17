"""Android foreground service — keeps BabbleCast eligible for mic while connected."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("babblecast.voice_service")
_stop = threading.Event()


def main() -> None:
    try:
        from jnius import autoclass

        PythonService = autoclass("org.kivy.android.PythonService")
        if PythonService.mService is not None:
            logger.info("BabbleCast Voice foreground service running")
    except Exception:
        logger.debug("Voice service JNI bootstrap skipped", exc_info=True)

    _stop.wait()


def request_stop() -> None:
    _stop.set()
