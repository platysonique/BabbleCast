"""Android network helpers for mDNS discovery on Wi‑Fi."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_multicast_lock = None


def _lock_held() -> bool:
    if _multicast_lock is None:
        return False
    try:
        return bool(_multicast_lock.isHeld())
    except Exception:
        return False


def _release_lock_quietly() -> None:
    global _multicast_lock
    if _multicast_lock is None:
        return
    try:
        if _multicast_lock.isHeld():
            _multicast_lock.release()
    except Exception:
        logger.debug("Stale multicast lock release failed", exc_info=True)
    _multicast_lock = None


def acquire_multicast_lock() -> bool:
    """Hold Wi‑Fi multicast lock so zeroconf browse packets are not dropped."""
    global _multicast_lock
    try:
        from kivy.utils import platform

        if platform != "android":
            return True
    except Exception:
        return True

    if _lock_held():
        return True

    _release_lock_quietly()

    try:
        from jnius import autoclass

        Context = autoclass("android.content.Context")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if activity is None:
            return False
        wifi = activity.getSystemService(Context.WIFI_SERVICE)
        lock = wifi.createMulticastLock("babblecast-mdns")
        lock.setReferenceCounted(True)
        lock.acquire()
        _multicast_lock = lock
        logger.info("Wi‑Fi multicast lock acquired for mDNS")
        return True
    except Exception:
        logger.exception("Failed to acquire Wi‑Fi multicast lock")
        _multicast_lock = None
        return False


def release_multicast_lock() -> None:
    _release_lock_quietly()
