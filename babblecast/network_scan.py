"""Scan physical LAN subnets for BabbleCast servers (port 9513)."""

from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from babblecast.constants import DEFAULT_WS_PORT
from babblecast.network import ipv4_prefix24, local_ipv4_addresses

logger = logging.getLogger(__name__)


def _port_open(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def lan_subnet_scan_targets() -> list[str]:
    """All /24 host addresses on subnets this device participates in."""
    prefixes: set[tuple[int, int, int]] = set()
    for ip in local_ipv4_addresses():
        prefix = ipv4_prefix24(ip)
        if prefix:
            prefixes.add(prefix)
    targets: list[str] = []
    for a, b, c in sorted(prefixes):
        for host in range(1, 255):
            targets.append(f"{a}.{b}.{c}.{host}")
    return targets


def scan_local_subnets_for_servers(
    ws_port: int = DEFAULT_WS_PORT,
    *,
    connect_timeout: float = 0.08,
    max_workers: int = 64,
) -> list[str]:
    """Probe local /24 LAN ranges for open BabbleCast WebSocket ports."""
    targets = lan_subnet_scan_targets()
    if not targets:
        return []
    found: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_port_open, ip, ws_port, connect_timeout): ip for ip in targets
        }
        for future in as_completed(futures):
            ip = futures[future]
            if future.result():
                found.append(ip)
    found.sort(key=lambda s: tuple(int(p) for p in s.split(".")))
    if found:
        logger.info("LAN subnet scan found %s server(s) on port %s", len(found), ws_port)
    return found
