"""Android runtime permissions for mic and network."""

from __future__ import annotations


def request_android_permissions() -> None:
    try:
        from kivy.utils import platform

        if platform != "android":
            return
        from android.permissions import Permission, request_permissions

        request_permissions(
            [
                Permission.INTERNET,
                Permission.RECORD_AUDIO,
                Permission.ACCESS_NETWORK_STATE,
                Permission.ACCESS_WIFI_STATE,
                Permission.CHANGE_WIFI_MULTICAST_STATE,
                Permission.ACCESS_FINE_LOCATION,
                Permission.BLUETOOTH_CONNECT,
            ]
        )
    except Exception:
        pass
