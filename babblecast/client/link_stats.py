"""Read-only connection stats for a bridged server link."""

from __future__ import annotations

from babblecast.active_tap_chats import get_active_tap_chat_store
from babblecast.client.bridge import ServerLinkState
from babblecast.client.session import ClientSession
from babblecast.network import is_local_host, is_private_lan_ipv4


def link_display_name(link: ServerLinkState) -> str:
    """User-facing server name without address suffix."""
    return (link.server_name or link.label).strip() or link.host


def build_link_info_rows(
    link: ServerLinkState,
    session: ClientSession | None,
    *,
    presence_count: int = 0,
    current_room_name: str = "",
    is_active: bool = False,
) -> list[tuple[str, str]]:
    """Label/value rows for server info dialogs."""
    rows: list[tuple[str, str]] = []
    rows.append(("Server name", link_display_name(link)))
    rows.append(("Address", f"{link.host}:{link.port}"))

    if session:
        rows.append(("WebSocket", f"{session.host}:{session.ws_port}"))
        rows.append(("Voice (UDP)", f"{session.host}:{session.server_udp_port}"))
        if session.local_udp_port:
            rows.append(("Your UDP port", str(session.local_udp_port)))
        rows.append(("Connected", "Yes" if session.connected else "No"))
        rows.append(("Your client ID", session.client_id or "—"))
        rows.append(("Server operator", "Yes" if session.is_server_operator else "No"))
        rows.append(
            ("Host password on server", "Yes" if session.host_password_protected else "No")
        )
        rows.append(
            ("Join password required", "Yes" if session.server_password_protected else "No")
        )
        if session.room_id:
            room_label = current_room_name or "Room"
            rows.append(("Current room", f"{room_label} ({session.room_id})"))
        else:
            rows.append(("Current room", "Not in a room"))
        if session.rooms:
            room_lines = []
            for room in session.rooms:
                name = str(room.get("name", "Room"))
                rid = str(room.get("room_id", ""))[:8]
                count = int(room.get("member_count", 0))
                lock = " 🔒" if room.get("password_protected") else ""
                room_lines.append(f"{name}{lock} ({count}) · {rid}…")
            rows.append(("Rooms on server", "\n".join(room_lines)))
        else:
            rows.append(("Rooms on server", "—"))
    else:
        rows.append(("Connected", "Yes" if link.connected else "No"))
        if link.client_id:
            rows.append(("Your client ID", link.client_id))

    rows.append(("Listen muted", "Yes" if link.listen_muted else "No"))
    rows.append(("Mic muted (this server)", "Yes" if link.mic_muted else "No"))
    rows.append(("Active server (UI)", "Yes" if is_active else "No"))
    rows.append(("People in room", str(presence_count) if presence_count else "—"))

    if is_private_lan_ipv4(link.host) or is_local_host(link.host):
        rows.append(("Network", "LAN / local"))
    else:
        rows.append(("Network", "Remote / routed"))

    tap_store = get_active_tap_chat_store()
    tap_threads = [
        c
        for c in tap_store.all_chats()
        if c.link_host == link.host and c.link_port == link.port
    ]
    if tap_threads:
        tap_lines = [
            f"{c.peer_name} ({len(c.messages)} msgs)" for c in tap_threads[:12]
        ]
        if len(tap_threads) > 12:
            tap_lines.append(f"… and {len(tap_threads) - 12} more")
        rows.append(("Saved tap chats", "\n".join(tap_lines)))
    else:
        rows.append(("Saved tap chats", "None"))

    rows.append(("Link ID", link.link_id[:12] + "…"))
    return rows


def format_link_info_text(rows: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    for label, value in rows:
        parts.append(f"{label}\n{value}")
    return "\n\n".join(parts)
