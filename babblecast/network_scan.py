"""Scan the BabbleCast subnet (11.2.9.x) for open voice servers."""

from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from babblecast.constants import DEFAULT_WS_PORT
from babblecast.network import babblecast_scan_targets

logger = logging.getLogger(__name__)


def _probe_host(ip: str, port: int, timeout: float) -> str | None:
    if ip.startswith("127."):
        return None
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return ip
    except OSError:
        return None


def scan_babblecast_subnet_for_servers(
    ws_port: int = DEFAULT_WS_PORT,
    *,
    connect_timeout: float = 0.12,
    max_workers: int = 64,
) -> list[str]:
    """TCP-probe only the BabbleCast subnet for an open WebSocket port."""
    targets = babblecast_scan_targets()
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
        logger.info(
            "BabbleCast subnet scan found %s server(s) on port %s",
            len(found),
            ws_port,
        )
    return found


# Back-compat alias used by discovery
scan_local_subnets_for_servers = scan_babblecast_subnet_for_servers


def merge_scan_with_client_subnets(scan_ips: list[str], client_ips=None) -> list[str]:
    """Scan results are already BabbleCast-subnet only — preserve order."""
    return list(scan_ips)
