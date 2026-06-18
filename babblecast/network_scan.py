"""Scan BabbleCast virtual domains (11.2.x.x) for open voice servers."""

from __future__ import annotations

import logging

from babblecast.address import discovery_scan_domains, is_babblecast_ip, scan_domains_for_servers, third_octet
from babblecast.constants import DEFAULT_WS_PORT
from babblecast.config import get_settings

logger = logging.getLogger(__name__)


def scan_babblecast_subnet_for_servers(
    ws_port: int = DEFAULT_WS_PORT,
    *,
    connect_timeout: float = 0.08,
    max_workers: int = 64,
) -> list[str]:
    """Probe BabbleCast domain octets in 11.2.x.x for open WebSocket ports."""
    settings = get_settings()
    domain_hint = None
    if settings.babblecast_ip:
        domain_hint = third_octet(settings.babblecast_ip)
    elif settings.babblecast_custom_address and settings.babblecast_address_suffix:
        from babblecast.address import parse_address_suffix

        try:
            domain_hint, _ = parse_address_suffix(settings.babblecast_address_suffix)
        except ValueError:
            domain_hint = None
    elif settings.last_server_host and is_babblecast_ip(settings.last_server_host):
        domain_hint = third_octet(settings.last_server_host)
    domains = discovery_scan_domains(domain_hint)
    found = scan_domains_for_servers(
        domains,
        ws_port=ws_port,
        connect_timeout=connect_timeout,
        max_workers=max_workers,
    )
    if found:
        logger.info("BabbleCast domain scan found %s server(s) on port %s", len(found), ws_port)
    return found


scan_local_subnets_for_servers = scan_babblecast_subnet_for_servers
