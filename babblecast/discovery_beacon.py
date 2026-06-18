"""UDP beacon for cross-subnet BabbleCast discovery on real LAN IPs."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time

from babblecast.constants import DEFAULT_WS_PORT, DISCOVERY_BEACON_PORT
from babblecast.network import primary_lan_ipv4

logger = logging.getLogger(__name__)

_DISCOVER_MAGIC = b"BABBLE_DISCOVER"
_BEACON_INTERVAL_SEC = 8.0
_LISTEN_SEC = 2.5

_beacon_names: dict[str, str] = {}
_lock = threading.Lock()


def beacon_server_name(lan_ip: str) -> str:
    with _lock:
        return _beacon_names.get(lan_ip.strip(), "")


def _register_beacon_server(lan_ip: str, name: str) -> None:
    lan_ip = lan_ip.strip()
    name = name.strip()
    if not lan_ip or not name:
        return
    with _lock:
        _beacon_names[lan_ip] = name


def _subnet_broadcast(ip: str) -> str | None:
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    return f"{parts[0]}.{parts[1]}.{parts[2]}.255"


def _local_broadcast_targets() -> list[str]:
    from babblecast.network import local_ipv4_addresses

    targets = {"255.255.255.255"}
    for ip in local_ipv4_addresses():
        bcast = _subnet_broadcast(ip)
        if bcast:
            targets.add(bcast)
    return sorted(targets)


def _encode_beacon(*, server_name: str, lan_ip: str, ws_port: int) -> bytes:
    payload = {
        "t": "bbc",
        "name": server_name,
        "lan": lan_ip,
        "ws": ws_port,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _parse_beacon(data: bytes) -> tuple[str, str, int] | None:
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if obj.get("t") != "bbc":
        return None
    name = str(obj.get("name", "")).strip()
    lan = str(obj.get("lan", "")).strip()
    if not lan:
        return None
    if not name:
        name = f"BabbleCast @ {lan}"
    ws_port = int(obj.get("ws", DEFAULT_WS_PORT) or DEFAULT_WS_PORT)
    return name, lan, ws_port


class DiscoveryBeacon:
    """Broadcast server name + LAN IP so clients on other /24 subnets can find us."""

    def __init__(
        self,
        *,
        server_name: str,
        ws_port: int = DEFAULT_WS_PORT,
        lan_ip: str = "",
    ) -> None:
        self._server_name = server_name.strip()
        self._ws_port = ws_port
        self._lan_ip = lan_ip.strip() or primary_lan_ipv4()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._server_name or not self._lan_ip or self._lan_ip.startswith("127."):
            logger.warning("Discovery beacon skipped — missing server name or LAN IP")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="bbc-udp-beacon")
        self._thread.start()
        logger.info(
            "Discovery beacon active %s @ %s (UDP %s)",
            self._server_name,
            self._lan_ip,
            DISCOVERY_BEACON_PORT,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except OSError:
                pass
            sock.bind(("", DISCOVERY_BEACON_PORT))
            sock.settimeout(0.5)
            next_beacon = 0.0
            while not self._stop.is_set():
                now = time.monotonic()
                if now >= next_beacon:
                    packet = _encode_beacon(
                        server_name=self._server_name,
                        lan_ip=self._lan_ip,
                        ws_port=self._ws_port,
                    )
                    for target in _local_broadcast_targets():
                        try:
                            sock.sendto(packet, (target, DISCOVERY_BEACON_PORT))
                        except OSError:
                            pass
                    next_beacon = now + _BEACON_INTERVAL_SEC
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if data == _DISCOVER_MAGIC:
                    reply = _encode_beacon(
                        server_name=self._server_name,
                        lan_ip=self._lan_ip,
                        ws_port=self._ws_port,
                    )
                    if addr and addr[0]:
                        try:
                            sock.sendto(reply, addr)
                        except OSError:
                            pass
        except OSError:
            logger.exception("Discovery beacon failed to bind UDP %s", DISCOVERY_BEACON_PORT)
        finally:
            sock.close()


def listen_for_beacons(timeout_sec: float = _LISTEN_SEC) -> list[tuple[str, str, int]]:
    """Collect server name + LAN IP from recent UDP beacons."""
    found: list[tuple[str, str, int]] = []
    seen: set[tuple[str, str, int]] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        sock.bind(("", DISCOVERY_BEACON_PORT))
        sock.settimeout(0.25)
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                data, _addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            parsed = _parse_beacon(data)
            if parsed and parsed not in seen:
                seen.add(parsed)
                found.append(parsed)
                _register_beacon_server(parsed[1], parsed[0])
    except OSError:
        logger.debug("Beacon listen unavailable on UDP %s", DISCOVERY_BEACON_PORT, exc_info=True)
    finally:
        sock.close()
    return found


def request_beacons(timeout_sec: float = _LISTEN_SEC) -> list[tuple[str, str, int]]:
    """Send discover probes and collect beacon replies."""
    from babblecast.mesh_probe import mesh_unicast_discover_targets
    from babblecast.network import saved_lan_hosts

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        targets = set(_local_broadcast_targets())
        for lan_ip in [*saved_lan_hosts(), *mesh_unicast_discover_targets()]:
            targets.add(lan_ip)
        for target in sorted(targets):
            try:
                sock.sendto(_DISCOVER_MAGIC, (target, DISCOVERY_BEACON_PORT))
            except OSError:
                pass
    finally:
        sock.close()
    return listen_for_beacons(timeout_sec)
