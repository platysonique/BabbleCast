"""LAN address helpers for mDNS advertisement and local-server detection."""

from __future__ import annotations

import array
import platform
import socket
import struct

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]


def local_ipv4_addresses(*, include_loopback: bool = False) -> list[str]:
    """Return non-loopback IPv4 addresses for this machine (deduped, stable order)."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add(ip: str) -> None:
        if not include_loopback and (ip.startswith("127.") or ip == "0.0.0.0"):
            return
        if ip not in seen:
            seen.add(ip)
            ordered.append(ip)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            add(s.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            add(info[4][0])
    except OSError:
        pass

    if platform.system() == "Linux":
        ordered.extend(_linux_interface_ipv4(seen))

    if not ordered and include_loopback:
        return ["127.0.0.1"]
    return ordered


def _linux_interface_ipv4(seen: set[str]) -> list[str]:
    """Enumerate IPv4 addresses via SIOCGIFCONF (no extra dependencies)."""
    if fcntl is None:
        return []
    found: list[str] = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_bytes = 32 * 32
        buf = array.array("B", b"\0" * max_bytes)
        iface = struct.pack("iL", max_bytes, buf.buffer_info()[0])
        result = fcntl.ioctl(sock.fileno(), 0x8912, iface)  # SIOCGIFCONF
        out_len = struct.unpack("iL", result)[0]
        data = buf.tobytes()[:out_len]
        sock.close()
        offset = 0
        while offset + 16 <= len(data):
            name = data[offset : offset + 16].split(b"\0", 1)[0].decode(errors="ignore")
            offset += 16
            if offset + 16 > len(data):
                break
            family, _, _, _, addr = struct.unpack("HHHL4s", data[offset : offset + 16])
            offset += 16
            if family != socket.AF_INET or not name:
                continue
            ip = socket.inet_ntoa(addr)
            if ip.startswith("127.") or ip in seen:
                continue
            seen.add(ip)
            found.append(ip)
    except Exception:
        pass
    return found


def ipv4_prefix24(ip: str) -> tuple[int, int, int] | None:
    """First three octets for typical home /24 LAN matching."""
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def same_subnet_24(a: str, b: str) -> bool:
    """True when two IPv4 addresses share a /24 prefix (typical home LAN)."""
    pa, pb = ipv4_prefix24(a), ipv4_prefix24(b)
    return pa is not None and pa == pb


def pick_reachable_server_ip(
    server_ips: list[str],
    *,
    client_ips: list[str] | None = None,
) -> str:
    """Pick the server IP most likely reachable from this machine."""
    client_ips = client_ips or local_ipv4_addresses()
    candidates = [ip for ip in server_ips if ip and not ip.startswith("127.")]
    if not candidates:
        return server_ips[0] if server_ips else ""
    for server_ip in candidates:
        for client_ip in client_ips:
            if same_subnet_24(server_ip, client_ip):
                return server_ip
    return candidates[0]


def is_private_lan_ipv4(ip: str) -> bool:
    """True for typical home/office private IPv4 ranges."""
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        a, b, _c, _d = (int(p) for p in parts)
    except ValueError:
        return False
    if a == 10:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    return False


def is_overlay_ipv4(ip: str) -> bool:
    """True for Tailscale/CGNAT 100.64.0.0/10 overlay addresses (not physical LAN)."""
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        a, b, _c, _d = (int(p) for p in parts)
    except ValueError:
        return False
    return a == 100 and 64 <= b <= 127


def advertise_hosts_for_settings() -> list[str]:
    """Real LAN IPv4 addresses for mDNS A records."""
    return [ip for ip in local_ipv4_addresses() if is_private_lan_ipv4(ip)]


def is_valid_connect_target(host: str) -> bool:
    """Hosts clients may dial: loopback, mDNS name, or private LAN IP."""
    normalized = host.strip().lower()
    if normalized in ("127.0.0.1", "localhost"):
        return True
    if normalized.endswith(".babblecast.local"):
        return True
    return is_private_lan_ipv4(host)


def primary_lan_ipv4() -> str:
    """Primary LAN IPv4 others on the network should use to reach this host."""
    hosts = advertise_hosts_for_settings()
    return hosts[0] if hosts else "127.0.0.1"


def is_local_host(host: str) -> bool:
    """True when host refers to this machine (loopback or a local interface IP)."""
    normalized = host.strip().lower()
    if normalized in ("127.0.0.1", "localhost", "::1"):
        return True
    try:
        socket.inet_aton(normalized)
    except OSError:
        return normalized.endswith(".babblecast.local")
    return normalized in local_ipv4_addresses()


def saved_lan_hosts() -> list[str]:
    """Previously used LAN IPs from settings (for beacon/scan hints)."""
    from babblecast.config import get_settings

    settings = get_settings()
    seen: set[str] = set()
    ordered: list[str] = []

    def add(ip: str) -> None:
        ip = ip.strip()
        if ip and is_private_lan_ipv4(ip) and ip not in seen:
            seen.add(ip)
            ordered.append(ip)

    add(settings.last_server_host)
    add(settings.last_server_underlay)
    return ordered
