"""Shared room list + chat persistence helpers for desktop and mobile clients."""

from __future__ import annotations

from typing import Any

from babblecast.protocol import is_name_taken_error, is_password_error
from babblecast.room_chat import ChatLine, get_room_chat_store


def resolve_room(
    link_id: str,
    session_room_id: str | None,
    room_by_link: dict[str, tuple[str, str]],
    *,
    default_name: str = "General",
) -> tuple[str, str]:
    if link_id in room_by_link:
        return room_by_link[link_id]
    if session_room_id:
        return session_room_id, default_name
    return "", default_name


def chat_lines(host: str, port: int, room_id: str) -> list[ChatLine]:
    if not room_id:
        return []
    return get_room_chat_store().lines(host, port, room_id)


def record_incoming_chat(
    host: str,
    port: int,
    room_id: str,
    data: dict[str, Any],
    *,
    room_name: str = "",
) -> ChatLine | None:
    text = str(data.get("text", ""))
    if not text.strip() or not room_id:
        return None
    return get_room_chat_store().append(
        host,
        port,
        room_id,
        str(data.get("name", "?")),
        text,
        client_id=str(data.get("client_id", "")),
        room_name=room_name,
    )


def purge_room_chat(host: str, port: int, room_id: str) -> None:
    if room_id:
        get_room_chat_store().purge(host, port, room_id)


def should_disconnect_failed_connect(
    error_code: str | None,
    message: str,
    *,
    connected: bool,
) -> bool:
    return not connected and (is_name_taken_error(error_code, message) or is_password_error(error_code, message))
