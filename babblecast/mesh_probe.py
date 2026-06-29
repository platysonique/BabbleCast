"""Mesh-aware underlay discovery without scanning full RFC1918 subnets."""

from __future__ import annotations

import logging
import subprocess

from babblecast.network import is_private_lan_ipv4, local_ipv4_addresses

logger = logging.getLogger(__name__)


def _ip_route_reachable(ip: str) -> bool:
    ip = ip.strip()
    if not is_private_lan_ipv4(ip):
        return False
    try:
        from kivy.utils import platform

        if platform == "android":
            from jnius import autoclass

            Runtime = autoclass("java.lang.Runtime")
            proc = Runtime.getRuntime().exec(["ip", "route", "get", ip])
            stream = proc.getInputStream()
            buf = bytearray(512)
            n = stream.read(buf)
            proc.waitFor()
            text = bytes(buf[: max(0, n)]).decode("utf-8", errors="ignore").lower()
            return "unreachable" not in text and "network is unreachable" not in text
    except Exception:
        logger.debug("Android route probe failed for %s", ip, exc_info=True)

    try:
        out = subprocess.check_output(
            ["ip", "route", "get", ip],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        ).lower()
        return "unreachable" not in out
    except (OSError, subprocess.SubprocessError):
        return False


def mesh_unicast_discover_targets() -> list[str]:
    """A few mesh-sibling LAN IPs worth a UDP discover unicast (not a /24 TCP scan)."""
    local = local_ipv4_addresses()
    if not local:
        return []
    parts = local[0].split(".")
    if len(parts) != 4:
        return []
    try:
        my_third = int(parts[2])
        my_fourth = int(parts[3])
    except ValueError:
        return []

    thirds = {1, 2, 10, my_third, 86, 100, 192}
    hosts = {1, my_fourth, 141}
    seen: set[str] = set()
    ordered: list[str] = []

    def add(ip: str) -> None:
        if ip not in seen and is_private_lan_ipv4(ip):
            seen.add(ip)
            ordered.append(ip)

    for third in sorted(thirds):
        for host in sorted(hosts):
            add(f"192.168.{third}.{host}")

    reachable = [ip for ip in ordered if _ip_route_reachable(ip)]
    if reachable:
        logger.info("Mesh route probe found %s reachable underlay target(s)", len(reachable))
    return reachable
