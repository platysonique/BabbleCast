"""mDNS service advertisement and discovery for BabbleCast servers."""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable

from zeroconf import IPVersion, ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from babblecast.constants import DEFAULT_UDP_PORT, DEFAULT_WS_PORT, DISCOVERY_STALE_SEC, SERVICE_TYPE

logger = logging.getLogger(__name__)


def _local_ips() -> list[str]:
    ips: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    ips.append("127.0.0.1")
    return list(dict.fromkeys(ips))


@dataclass(frozen=True)
class DiscoveredServer:
    name: str
    host: str
    ws_port: int
    udp_port: int
    properties: dict[str, str]
    seen_at: float

    @property
    def label(self) -> str:
        return f"{self.name} ({self.host}:{self.ws_port})"


class ServerAdvertiser:
    """Publish a BabbleCast server on the local network."""

    def __init__(
        self,
        server_name: str,
        ws_port: int = DEFAULT_WS_PORT,
        udp_port: int = DEFAULT_UDP_PORT,
        host: str | None = None,
    ) -> None:
        self._server_name = server_name
        self._ws_port = ws_port
        self._udp_port = udp_port
        self._host = host or _local_ips()[0]
        self._zc: Zeroconf | None = None
        self._info: ServiceInfo | None = None

    def start(self) -> None:
        if self._zc is not None:
            return
        safe = self._server_name.replace(" ", "-").lower()
        self._zc = Zeroconf(ip_version=IPVersion.V4Only)
        self._info = ServiceInfo(
            SERVICE_TYPE,
            f"{safe}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(self._host)],
            port=self._ws_port,
            properties={
                "name": self._server_name,
                "udp": str(self._udp_port),
                "ver": "1",
            },
            server=f"{safe}.local.",
        )
        self._zc.register_service(self._info)
        logger.info("Advertising BabbleCast server %s on %s:%s", self._server_name, self._host, self._ws_port)

    def stop(self) -> None:
        if self._zc and self._info:
            try:
                self._zc.unregister_service(self._info)
            except Exception:
                logger.exception("Failed to unregister mDNS service")
            self._zc.close()
        self._zc = None
        self._info = None


class ServerDiscovery:
    """Browse for BabbleCast servers on LAN / Tailscale."""

    def __init__(self, on_update: Callable[[list[DiscoveredServer]], None] | None = None) -> None:
        self._on_update = on_update
        self._servers: dict[str, DiscoveredServer] = {}
        self._lock = threading.Lock()
        self._zc: Zeroconf | None = None
        self._browser: ServiceBrowser | None = None
        self._prune_thread: threading.Thread | None = None
        self._running = False

    @property
    def servers(self) -> list[DiscoveredServer]:
        with self._lock:
            return sorted(self._servers.values(), key=lambda s: s.name.lower())

    def _emit(self) -> None:
        if self._on_update:
            self._on_update(self.servers)

    def _resolve(self, name: str, info: ServiceInfo) -> None:
        host = socket.inet_ntoa(info.addresses[0]) if info.addresses else ""
        if not host:
            return
        props = {k.decode() if isinstance(k, bytes) else k: (v.decode() if isinstance(v, bytes) else str(v)) for k, v in info.properties.items()}
        display = props.get("name", name.split(".")[0].replace("-", " "))
        udp_port = int(props.get("udp", DEFAULT_UDP_PORT))
        entry = DiscoveredServer(
            name=display,
            host=host,
            ws_port=info.port or DEFAULT_WS_PORT,
            udp_port=udp_port,
            properties=props,
            seen_at=time.time(),
        )
        with self._lock:
            self._servers[host] = entry
        self._emit()

    def _on_service(self, zc: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
        if state_change is ServiceStateChange.Removed:
            return
        info = zc.get_service_info(service_type, name, timeout=2000)
        if info:
            self._resolve(name, info)

    def _prune_loop(self) -> None:
        while self._running:
            time.sleep(5)
            cutoff = time.time() - DISCOVERY_STALE_SEC
            changed = False
            with self._lock:
                stale = [k for k, v in self._servers.items() if v.seen_at < cutoff]
                for k in stale:
                    del self._servers[k]
                    changed = True
            if changed:
                self._emit()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._zc = Zeroconf(ip_version=IPVersion.V4Only)
        self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, handlers=[self._on_service])
        self._prune_thread = threading.Thread(target=self._prune_loop, daemon=True, name="bbc-discovery-prune")
        self._prune_thread.start()
        logger.info("Browsing for BabbleCast servers")

    def stop(self) -> None:
        self._running = False
        if self._browser:
            self._browser.cancel()
            self._browser = None
        if self._zc:
            self._zc.close()
            self._zc = None
