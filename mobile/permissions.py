"""Android runtime permissions for mic and network."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _android_api_level() -> int:
    try:
        from jnius import autoclass

        version = autoclass("android.os.Build$VERSION")
        return int(version.SDK_INT)
    except Exception:
        return 0


def record_audio_granted() -> bool:
    try:
        from kivy.utils import platform

        if platform != "android":
            return True
        from android.permissions import Permission, check_permission

        return bool(check_permission(Permission.RECORD_AUDIO))
    except Exception:
        logger.exception("RECORD_AUDIO permission check failed — treating as denied")
        return False


def request_android_permissions() -> None:
    try:
        from kivy.utils import platform

        if platform != "android":
            return
        from android.permissions import Permission, check_permission, request_permissions

        needed = [
            Permission.INTERNET,
            Permission.RECORD_AUDIO,
            Permission.ACCESS_NETWORK_STATE,
            Permission.ACCESS_WIFI_STATE,
            Permission.CHANGE_WIFI_MULTICAST_STATE,
            Permission.ACCESS_FINE_LOCATION,
        ]
        if _android_api_level() >= 31:
            needed.append(Permission.BLUETOOTH_CONNECT)
        if _android_api_level() >= 33:
            needed.append(Permission.NEARBY_WIFI_DEVICES)
        request_permissions(needed)
        if not check_permission(Permission.ACCESS_FINE_LOCATION):
            logger.warning(
                "Location permission not granted — LAN discovery may be empty on Android. "
                "Use manual IP below or grant Location in system settings."
            )
    except Exception:
        logger.exception("Android permission request failed")


def location_granted() -> bool:
    try:
        from kivy.utils import platform

        if platform != "android":
            return True
        from android.permissions import Permission, check_permission

        return bool(check_permission(Permission.ACCESS_FINE_LOCATION))
    except Exception:
        return True
