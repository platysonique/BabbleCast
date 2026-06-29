"""Platform TCP probes used by BabbleCast LAN scanning."""

from __future__ import annotations

import socket


def tcp_port_open(ip: str, port: int, timeout: float) -> bool:
    try:
        from kivy.utils import platform
    except ImportError:
        platform = "unknown"

    if platform == "android":
        try:
            from mobile.android_connect import port_open as android_port_open

            return android_port_open(ip, port, timeout)
        except ImportError:
            pass

    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False
