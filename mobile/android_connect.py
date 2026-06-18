"""Android TCP probes that bypass VPN tunnels for LAN scans."""

from __future__ import annotations

import logging
import socket
import time

logger = logging.getLogger(__name__)

# JNI + Wi‑Fi network are expensive to resolve; cache them instead of per-probe setup.
_cache: dict[str, object] = {}
_WIFI_CACHE_TTL_SEC = 30.0


def _clear_cache() -> None:
    _cache.clear()


def _android_wifi_network():
    """Return the active Wi‑Fi ``Network`` object, refreshing periodically."""
    now = time.monotonic()
    cached = _cache.get("wifi_net")
    cached_at = float(_cache.get("wifi_at", 0.0))
    if cached is not None and now - cached_at < _WIFI_CACHE_TTL_SEC:
        return cached

    try:
        from kivy.utils import platform

        if platform != "android":
            return None
        from jnius import autoclass

        if "ConnectivityManager" not in _cache:
            _cache["Context"] = autoclass("android.content.Context")
            _cache["ConnectivityManager"] = autoclass("android.net.ConnectivityManager")
            _cache["InetSocketAddress"] = autoclass("java.net.InetSocketAddress")
            _cache["JavaSocket"] = autoclass("java.net.Socket")
            _cache["PythonActivity"] = autoclass("org.kivy.android.PythonActivity")

        Context = _cache["Context"]
        ConnectivityManager = _cache["ConnectivityManager"]
        PythonActivity = _cache["PythonActivity"]

        activity = PythonActivity.mActivity
        if activity is None:
            return None
        cm = activity.getSystemService(Context.CONNECTIVITY_SERVICE)
        if cm is None:
            return None

        transport_wifi = getattr(ConnectivityManager, "TRANSPORT_WIFI", 1)
        wifi_net = None
        for net in cm.getAllNetworks():
            caps = cm.getNetworkCapabilities(net)
            if caps is not None and caps.hasTransport(transport_wifi):
                wifi_net = net
                break
        if wifi_net is None:
            return None

        _cache["wifi_net"] = wifi_net
        _cache["wifi_at"] = now
        return wifi_net
    except Exception:
        logger.debug("Wi‑Fi network lookup failed", exc_info=True)
        _clear_cache()
        return None


def port_open_on_wifi(ip: str, port: int, timeout: float) -> bool | None:
    """Try TCP connect on the Wi‑Fi network (not VPN). Returns None if unavailable."""
    wifi_net = _android_wifi_network()
    if wifi_net is None:
        return None
    if "JavaSocket" not in _cache or "InetSocketAddress" not in _cache:
        return None
    try:
        JavaSocket = _cache["JavaSocket"]
        InetSocketAddress = _cache["InetSocketAddress"]
        sock = JavaSocket()
        try:
            wifi_net.bindSocket(sock)
            timeout_ms = max(1, int(timeout * 1000))
            sock.connect(InetSocketAddress(ip, int(port)), timeout_ms)
            return True
        except Exception:
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass
    except Exception:
        logger.debug("Wi‑Fi-bound TCP probe failed", exc_info=True)
        _clear_cache()
        return None


def port_open(ip: str, port: int, timeout: float) -> bool:
    """TCP port probe; on Android prefers Wi‑Fi so VPN does not steal LAN traffic."""
    wifi_result = port_open_on_wifi(ip, port, timeout)
    if wifi_result is not None:
        return wifi_result
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False
