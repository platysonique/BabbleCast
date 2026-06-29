"""LAN discovery — mDNS supplement via UDP beacon and mesh-aware TCP probes."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from babblecast.constants import DEFAULT_WS_PORT
from babblecast.network import is_private_lan_ipv4, saved_lan_hosts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LanServerHit:
    host: str
    name: str
    ws_port: int


def _is_android() -> bool:
    try:
        from kivy.utils import platform

        return platform == "android"
    except ImportError:
        return False


def _scan_connect_timeout() -> float:
    return 0.12 if _is_android() else 0.08


def discover_lan_servers(
    ws_port: int = DEFAULT_WS_PORT,
    *,
    connect_timeout: float | None = None,
) -> list[LanServerHit]:
    """Find BabbleCast servers on the home LAN (cross-subnet via beacon + mesh probe)."""
    if connect_timeout is None:
        connect_timeout = _scan_connect_timeout()

    from babblecast.discovery_beacon import beacon_server_name, request_beacons
    from babblecast.mesh_probe import mesh_unicast_discover_targets
    from babblecast.transport_probe import tcp_port_open

    hits: dict[str, LanServerHit] = {}

    def add(host: str, name: str, port: int = ws_port) -> None:
        host = host.strip()
        if not is_private_lan_ipv4(host):
            return
        if not tcp_port_open(host, port, connect_timeout):
            return
        label = name.strip() or beacon_server_name(host) or f"BabbleCast @ {host}"
        hits[host] = LanServerHit(host=host, name=label, ws_port=port)

    try:
        for server_name, lan_ip, port in request_beacons():
            add(lan_ip, server_name, port or ws_port)
    except Exception:
        logger.debug("UDP beacon discovery unavailable", exc_info=True)

    for lan_ip in [*saved_lan_hosts(), *mesh_unicast_discover_targets()]:
        add(lan_ip, beacon_server_name(lan_ip))

    if hits:
        logger.info("LAN discovery found %s server(s) on port %s", len(hits), ws_port)
    return sorted(hits.values(), key=lambda h: (h.name.lower(), h.host))


# Back-compat aliases
scan_local_subnets_for_servers = discover_lan_servers
scan_babblecast_subnet_for_servers = discover_lan_servers
