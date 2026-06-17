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
    service_name: str
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
    """Publish a BabbleCast server on the local network.

    Runs zeroconf in a dedicated thread so it never conflicts with asyncio
    event loops (embedded server, headless server, Qt main thread).
    """

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
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._ready_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="bbc-mdns-advertise",
        )
        self._thread.start()
        if not self._ready_event.wait(timeout=10):
            raise RuntimeError("mDNS advertiser failed to start within 10s")

    def _run(self) -> None:
        zc: Zeroconf | None = None
        info: ServiceInfo | None = None
        try:
            safe = self._server_name.replace(" ", "-").lower()
            zc = Zeroconf(ip_version=IPVersion.V4Only)
            info = ServiceInfo(
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
            zc.register_service(info)
            self._zc = zc
            self._info = info
            self._ready_event.set()
            logger.info(
                "Advertising BabbleCast server %s on %s:%s",
                self._server_name,
                self._host,
                self._ws_port,
            )
            self._stop_event.wait()
        except Exception:
            self._ready_event.set()
            logger.exception("mDNS advertiser thread failed")
        finally:
            if zc and info:
                try:
                    zc.unregister_service(info)
                except Exception:
                    logger.exception("Failed to unregister mDNS service")
                zc.close()
            self._zc = None
            self._info = None

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        self._thread = None


class ServerDiscovery:
    """Browse for BabbleCast servers on LAN / Tailscale.

    Runs zeroconf in a dedicated thread for the same asyncio-safety reasons
    as ServerAdvertiser.
    """

    def __init__(self, on_update: Callable[[list[DiscoveredServer]], None] | None = None) -> None:
        self._on_update = on_update
        self._servers: dict[str, DiscoveredServer] = {}
        self._lock = threading.Lock()
        self._zc: Zeroconf | None = None
        self._browser: ServiceBrowser | None = None
        self._thread: threading.Thread | None = None
        self._prune_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

    @property
    def servers(self) -> list[DiscoveredServer]:
        with self._lock:
            return sorted(self._servers.values(), key=lambda s: s.name.lower())

    def _emit(self) -> None:
        if self._on_update:
            self._on_update(self.servers)

    def _resolve(self, service_name: str, info: ServiceInfo) -> None:
        host = socket.inet_ntoa(info.addresses[0]) if info.addresses else ""
        if not host:
            return
        props = {k.decode() if isinstance(k, bytes) else k: (v.decode() if isinstance(v, bytes) else str(v)) for k, v in info.properties.items()}
        display = props.get("name", service_name.split(".")[0].replace("-", " "))
        udp_port = int(props.get("udp", DEFAULT_UDP_PORT))
        entry = DiscoveredServer(
            service_name=service_name,
            name=display,
            host=host,
            ws_port=info.port or DEFAULT_WS_PORT,
            udp_port=udp_port,
            properties=props,
            seen_at=time.time(),
        )
        with self._lock:
            self._servers[service_name] = entry
        self._emit()

    def _on_service(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is ServiceStateChange.Removed:
            with self._lock:
                removed = self._servers.pop(name, None)
            if removed:
                self._emit()
            return
        info = zeroconf.get_service_info(service_type, name, timeout=2000)
        if info:
            self._resolve(name, info)

    def _prune_loop(self) -> None:
        """Fallback for servers that stop without a clean mDNS Removed event."""
        while not self._stop_event.is_set():
            self._stop_event.wait(30)
            if self._stop_event.is_set():
                break
            cutoff = time.time() - DISCOVERY_STALE_SEC
            changed = False
            with self._lock:
                stale = [k for k, v in self._servers.items() if v.seen_at < cutoff]
                for k in stale:
                    del self._servers[k]
                    changed = True
            if changed:
                self._emit()

    def _browse_loop(self) -> None:
        zc: Zeroconf | None = None
        browser: ServiceBrowser | None = None
        try:
            zc = Zeroconf(ip_version=IPVersion.V4Only)
            browser = ServiceBrowser(zc, SERVICE_TYPE, handlers=[self._on_service])
            self._zc = zc
            self._browser = browser
            logger.info("Browsing for BabbleCast servers")
            self._stop_event.wait()
        except Exception:
            logger.exception("mDNS discovery thread failed")
        finally:
            if browser:
                browser.cancel()
            if zc:
                zc.close()
            self._browser = None
            self._zc = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._browse_loop,
            daemon=True,
            name="bbc-mdns-browse",
        )
        self._thread.start()
        self._prune_thread = threading.Thread(
            target=self._prune_loop,
            daemon=True,
            name="bbc-discovery-prune",
        )
        self._prune_thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        if self._prune_thread:
            self._prune_thread.join(timeout=5)
            self._prune_thread = None
