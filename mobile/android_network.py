"""Android network helpers for mDNS discovery on Wi‑Fi."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_multicast_lock = None


def acquire_multicast_lock() -> None:
    """Hold Wi‑Fi multicast lock so zeroconf browse packets are not dropped."""
    global _multicast_lock
    try:
        from kivy.utils import platform

        if platform != "android":
            return
        if _multicast_lock is not None:
            return
        from jnius import autoclass

        Context = autoclass("android.content.Context")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if activity is None:
            return
        wifi = activity.getSystemService(Context.WIFI_SERVICE)
        lock = wifi.createMulticastLock("babblecast-mdns")
        lock.setReferenceCounted(True)
        lock.acquire()
        _multicast_lock = lock
        logger.info("Wi‑Fi multicast lock acquired for mDNS")
    except Exception:
        logger.exception("Failed to acquire Wi‑Fi multicast lock")


def release_multicast_lock() -> None:
    global _multicast_lock
    try:
        if _multicast_lock is not None:
            _multicast_lock.release()
            _multicast_lock = None
    except Exception:
        logger.exception("Failed to release Wi‑Fi multicast lock")
