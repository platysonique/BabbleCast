"""Fallback LAN scan when mDNS browse finds nothing (AP isolation, VLANs, etc.)."""

from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from babblecast.constants import DEFAULT_WS_PORT
from babblecast.network import local_ipv4_addresses, same_subnet_24

logger = logging.getLogger(__name__)


def _probe_host(ip: str, port: int, timeout: float) -> str | None:
    if ip.startswith("127."):
        return None
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return ip
    except OSError:
        return None


def scan_local_subnets_for_servers(
    ws_port: int = DEFAULT_WS_PORT,
    *,
    connect_timeout: float = 0.12,
    max_workers: int = 64,
) -> list[str]:
    """TCP-probe the /24 around each local interface for an open BabbleCast WS port.

    This is the fallback when mDNS cannot cross wired↔Wi‑Fi boundaries or the
    router blocks multicast. It does not replace mDNS — it fills the gap when
    browse returns empty.
    """
    client_ips = local_ipv4_addresses()
    if not client_ips:
        return []

    targets: list[str] = []
    seen: set[str] = set()
    for client_ip in client_ips:
        prefix = ".".join(client_ip.split(".")[:3])
        for last in range(1, 255):
            candidate = f"{prefix}.{last}"
            if candidate == client_ip or candidate in seen:
                continue
            seen.add(candidate)
            targets.append(candidate)

    found: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_host, ip, ws_port, connect_timeout): ip for ip in targets
        }
        for future in as_completed(futures):
            ip = future.result()
            if ip:
                found.append(ip)

    found.sort(key=lambda s: tuple(int(p) for p in s.split(".")))
    if found:
        logger.info("Subnet scan found %s BabbleCast port(s) open on %s", len(found), ws_port)
    return found


def merge_scan_with_client_subnets(scan_ips: list[str], client_ips: list[str] | None = None) -> list[str]:
    """Prefer scan hits on the same /24 as a local interface."""
    client_ips = client_ips or local_ipv4_addresses()
    same: list[str] = []
    other: list[str] = []
    for ip in scan_ips:
        if any(same_subnet_24(ip, c) for c in client_ips):
            same.append(ip)
        else:
            other.append(ip)
    return same + other
