"""mDNS service advertisement and discovery for BabbleCast servers."""

from __future__ import annotations

import logging
import re
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable

from zeroconf import IPVersion, InterfaceChoice, ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from babblecast.constants import DEFAULT_UDP_PORT, DEFAULT_WS_PORT, DISCOVERY_STALE_SEC, LOCAL_DOMAIN, SERVICE_TYPE
from babblecast.address import is_babblecast_ip
from babblecast.network import pick_reachable_server_ip
from babblecast.network_scan import scan_local_subnets_for_servers

logger = logging.getLogger(__name__)


def slugify_server_name(name: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return safe or "babblecast"


def service_hostname(slug: str) -> str:
    return f"{slug}.{LOCAL_DOMAIN}"


@dataclass(frozen=True)
class DiscoveredServer:
    service_name: str
    name: str
    host: str
    ws_port: int
    udp_port: int
    properties: dict[str, str]
    seen_at: float
    addresses: tuple[str, ...] = ()
    discovered_via: str = "mdns"

    @property
    def label(self) -> str:
        host_label = self.hostname or f"{self.host}:{self.ws_port}"
        via = " · scan" if self.discovered_via == "scan" else ""
        return f"{self.name} ({host_label}){via}"

    @property
    def hostname(self) -> str:
        slug = self.properties.get("host", "")
        if slug:
            return service_hostname(slug)
        return ""

    @property
    def password_required(self) -> bool:
        return self.properties.get("auth", "0") == "1"

    @property
    def connect_host(self) -> str:
        """Hostname or subnet-aware IP for WebSocket connect."""
        if self.hostname:
            return self.hostname
        if self.addresses:
            return pick_reachable_server_ip(list(self.addresses))
        return self.host


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
        hosts: list[str] | None = None,
        *,
        password_protected: bool = False,
    ) -> None:
        self._server_name = server_name
        self._ws_port = ws_port
        self._udp_port = udp_port
        self._hosts = hosts if hosts is not None else local_ipv4_addresses()
        self._password_protected = password_protected
        self._slug = slugify_server_name(server_name)
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
            addresses = []
            for host in self._hosts:
                try:
                    addresses.append(socket.inet_aton(host))
                except OSError:
                    continue
            if not addresses:
                addresses = [socket.inet_aton("127.0.0.1")]
            zc = Zeroconf(ip_version=IPVersion.V4Only, interfaces=InterfaceChoice.All)
            hostname = f"{self._slug}.{LOCAL_DOMAIN}."
            info = ServiceInfo(
                SERVICE_TYPE,
                f"{self._slug}.{SERVICE_TYPE}",
                addresses=addresses,
                port=self._ws_port,
                properties={
                    "name": self._server_name,
                    "udp": str(self._udp_port),
                    "ver": "1",
                    "host": self._slug,
                    "auth": "1" if self._password_protected else "0",
                },
                server=hostname,
            )
            zc.register_service(info)
            self._zc = zc
            self._info = info
            self._ready_event.set()
            logger.info(
                "Advertising BabbleCast server %s as %s on %s:%s (IPs: %s)",
                self._server_name,
                service_hostname(self._slug),
                self._hosts,
                self._ws_port,
                ", ".join(self._hosts) or "127.0.0.1",
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
        self._scan_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._scan_done = False

    @property
    def servers(self) -> list[DiscoveredServer]:
        with self._lock:
            return sorted(self._servers.values(), key=lambda s: s.name.lower())

    def _emit(self) -> None:
        if self._on_update:
            self._on_update(self.servers)

    def _resolve(self, service_name: str, info: ServiceInfo) -> None:
        raw_addresses = [socket.inet_ntoa(addr) for addr in (info.addresses or [])]
        non_loopback = [ip for ip in raw_addresses if not ip.startswith("127.")]
        babblecast_pool = [ip for ip in non_loopback if is_babblecast_ip(ip)]
        address_pool = babblecast_pool or non_loopback or raw_addresses
        host = pick_reachable_server_ip(address_pool) if address_pool else ""
        if not host:
            return
        props = {
            k.decode() if isinstance(k, bytes) else k: (v.decode() if isinstance(v, bytes) else str(v))
            for k, v in info.properties.items()
        }
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
            addresses=tuple(address_pool),
            discovered_via="mdns",
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

    def _scan_loop(self) -> None:
        """When mDNS browse is empty, probe BabbleCast virtual domains for open WS ports."""
        while not self._stop_event.is_set():
            self._stop_event.wait(15)
            if self._stop_event.is_set() or self._scan_done:
                break
            with self._lock:
                if self._servers:
                    self._scan_done = True
                    break
            try:
                hits = scan_local_subnets_for_servers()
            except Exception:
                logger.exception("Subnet scan failed")
                hits = []
            if not hits:
                continue
            now = time.time()
            changed = False
            with self._lock:
                for ip in hits:
                    key = f"scan:{ip}"
                    if key in self._servers:
                        continue
                    self._servers[key] = DiscoveredServer(
                        service_name=key,
                        name=f"BabbleCast @ {ip}",
                        host=ip,
                        ws_port=DEFAULT_WS_PORT,
                        udp_port=DEFAULT_UDP_PORT,
                        properties={"name": f"BabbleCast @ {ip}", "host": "", "auth": "0"},
                        seen_at=now,
                        addresses=(ip,),
                        discovered_via="scan",
                    )
                    changed = True
                self._scan_done = True
            if changed:
                logger.info("Subnet scan added %s server(s)", len(hits))
                self._emit()
            break

    def _browse_loop(self) -> None:
        zc: Zeroconf | None = None
        browser: ServiceBrowser | None = None
        try:
            zc = Zeroconf(ip_version=IPVersion.V4Only, interfaces=InterfaceChoice.All)
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
        self._scan_thread = threading.Thread(
            target=self._scan_loop,
            daemon=True,
            name="bbc-subnet-scan",
        )
        self._scan_thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._on_update = None
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        if self._prune_thread:
            self._prune_thread.join(timeout=5)
            self._prune_thread = None
        if self._scan_thread:
            self._scan_thread.join(timeout=60)
            self._scan_thread = None
        self._scan_done = False
