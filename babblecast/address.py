"""Legacy BabbleCast virtual addressing (11.2.x.x) — kept for migration tests only."""

from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from babblecast.constants import DEFAULT_WS_PORT

logger = logging.getLogger(__name__)

BABBLECAST_FIXED_OCTETS = (11, 2)
BABBLECAST_AUTO_DOMAIN = 9


def babblecast_prefix() -> str:
    return ".".join(str(o) for o in BABBLECAST_FIXED_OCTETS)


def babblecast_auto_subnet() -> str:
    """Subnet used when custom address is off — always ``11.2.9.x``."""
    return f"{babblecast_prefix()}.{BABBLECAST_AUTO_DOMAIN}.x"


def format_babblecast_ip(third: int, fourth: int) -> str:
    return f"{babblecast_prefix()}.{third}.{fourth}"


def is_babblecast_ip(ip: str) -> bool:
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        octets = tuple(int(p) for p in parts)
    except ValueError:
        return False
    if octets[:2] != BABBLECAST_FIXED_OCTETS:
        return False
    return all(1 <= o <= 254 for o in octets[2:])


def parse_address_suffix(suffix: str) -> tuple[int | None, int | None]:
    """Parse user suffix after ``11.2.`` — ``9`` or ``9.10``."""
    cleaned = suffix.strip().strip(".")
    if not cleaned:
        return None, None
    parts = cleaned.split(".")
    if len(parts) > 2:
        raise ValueError("Use at most two numbers after 11.2. (e.g. 9 or 9.10)")
    try:
        third = int(parts[0])
        fourth = int(parts[1]) if len(parts) == 2 else None
    except ValueError as exc:
        raise ValueError("Address suffix must be numbers only") from exc
    for label, value in (("domain", third), ("host", fourth)):
        if value is not None and not (1 <= value <= 254):
            raise ValueError(f"{label} octet must be 1–254")
    return third, fourth


def validate_address_suffix(suffix: str) -> str | None:
    try:
        parse_address_suffix(suffix)
        return None
    except ValueError as exc:
        return str(exc)


def _port_open(ip: str, port: int, timeout: float) -> bool:
    try:
        from babblecast.transport_probe import tcp_port_open

        return tcp_port_open(ip, port, timeout)
    except ImportError:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except OSError:
            return False


def _first_free_host_in_domain(third: int, *, port: int = DEFAULT_WS_PORT, timeout: float = 0.08) -> int | None:
    for fourth in range(1, 255):
        ip = format_babblecast_ip(third, fourth)
        if not _port_open(ip, port, timeout):
            return fourth
    return None


def allocate_babblecast_ip(
    *,
    custom: bool,
    suffix: str = "",
    port: int = DEFAULT_WS_PORT,
) -> str:
    """Resolve the BabbleCast IP for this host (custom or auto-dynamic)."""
    if custom:
        third, fourth = parse_address_suffix(suffix)
        if third is None:
            raise ValueError("Enter a custom address suffix (e.g. 9 or 9.10)")
        if fourth is not None:
            ip = format_babblecast_ip(third, fourth)
            if _port_open(ip, port, 0.08):
                raise ValueError(f"{ip} is already in use — pick another host id")
            return ip
        host = _first_free_host_in_domain(third, port=port)
        if host is None:
            raise ValueError(f"No free addresses left in 11.2.{third}.x")
        return format_babblecast_ip(third, host)

    host = _first_free_host_in_domain(BABBLECAST_AUTO_DOMAIN, port=port)
    if host is None:
        raise RuntimeError(f"No free BabbleCast address found in {babblecast_auto_subnet()}")
    return format_babblecast_ip(BABBLECAST_AUTO_DOMAIN, host)


def domain_scan_targets(third: int) -> list[str]:
    return [format_babblecast_ip(third, h) for h in range(1, 255)]


def scan_hosts_for_servers(
    hosts: list[str],
    *,
    ws_port: int = DEFAULT_WS_PORT,
    connect_timeout: float = 0.08,
    max_workers: int = 64,
) -> list[str]:
    if not hosts:
        return []
    workers = min(max_workers, max(1, len(hosts)))
    found: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_port_open, ip, ws_port, connect_timeout): ip for ip in hosts
        }
        for future in as_completed(futures):
            ip = futures[future]
            if future.result():
                found.append(ip)
    found.sort(key=lambda s: tuple(int(p) for p in s.split(".")))
    return found


def scan_domains_for_servers(
    domains: list[int],
    *,
    ws_port: int = DEFAULT_WS_PORT,
    connect_timeout: float = 0.08,
    max_workers: int = 64,
) -> list[str]:
    targets: list[str] = []
    for d in domains:
        if 1 <= d <= 254:
            targets.extend(domain_scan_targets(d))
    return scan_hosts_for_servers(
        targets,
        ws_port=ws_port,
        connect_timeout=connect_timeout,
        max_workers=max_workers,
    )


def discovery_scan_domains(settings_domain: int | None = None) -> list[int]:
    """Domain octets to probe when mDNS is empty (auto pool + optional custom)."""
    domains: list[int] = [BABBLECAST_AUTO_DOMAIN]
    if settings_domain and settings_domain != BABBLECAST_AUTO_DOMAIN:
        domains.insert(0, settings_domain)
    return domains


def third_octet(ip: str) -> int | None:
    if not is_babblecast_ip(ip):
        return None
    return int(ip.split(".")[2])
