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
