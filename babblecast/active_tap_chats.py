"""Persist active tap chat threads until explicitly cleared."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from babblecast.paths import app_config_dir


def _active_taps_path(*, create: bool = False) -> Path:
    return app_config_dir(create=create) / "active_tap_chats.json"


@dataclass
class ActiveTapChat:
    tap_id: str
    link_host: str
    link_port: int
    peer_id: str
    peer_name: str
    server_label: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def preview(self) -> str:
        if self.messages:
            last = self.messages[-1]
            text = str(last.get("text", "")).strip()
            if text:
                return text[:48]
        return f"Tap with {self.peer_name}"


class ActiveTapChatStore:
    def __init__(self) -> None:
        self._by_id: dict[str, ActiveTapChat] = {}
        self.load()

    def load(self) -> None:
        path = _active_taps_path()
        if not path.exists():
            self._by_id = {}
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._by_id = {}
            for x in raw.get("chats", []):
                chat = ActiveTapChat(
                    tap_id=str(x.get("tap_id", "")),
                    link_host=str(x.get("link_host", "")),
                    link_port=int(x.get("link_port", 0)),
                    peer_id=str(x.get("peer_id", "")),
                    peer_name=str(x.get("peer_name", "")),
                    server_label=str(x.get("server_label", "")),
                    messages=list(x.get("messages", [])),
                    created_at=float(x.get("created_at", time.time())),
                    updated_at=float(x.get("updated_at", time.time())),
                )
                if chat.tap_id:
                    self._by_id[chat.tap_id] = chat
        except (json.JSONDecodeError, TypeError, ValueError):
            self._by_id = {}

    def save(self) -> None:
        path = _active_taps_path(create=True)
        chats = sorted(self._by_id.values(), key=lambda c: c.updated_at, reverse=True)
        payload = {"chats": [asdict(c) for c in chats]}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get(self, tap_id: str) -> ActiveTapChat | None:
        return self._by_id.get(tap_id)

    def all_chats(self) -> list[ActiveTapChat]:
        return sorted(self._by_id.values(), key=lambda c: c.updated_at, reverse=True)

    def record_received(
        self,
        *,
        tap_id: str,
        link_host: str,
        link_port: int,
        peer_id: str,
        peer_name: str,
        server_label: str,
    ) -> ActiveTapChat:
        existing = self._by_id.get(tap_id)
        if existing:
            existing.peer_id = peer_id
            existing.peer_name = peer_name
            existing.server_label = server_label
            existing.link_host = link_host
            existing.link_port = link_port
            existing.updated_at = time.time()
            self.save()
            return existing
        chat = ActiveTapChat(
            tap_id=tap_id,
            link_host=link_host,
            link_port=link_port,
            peer_id=peer_id,
            peer_name=peer_name,
            server_label=server_label,
        )
        self._by_id[tap_id] = chat
        self.save()
        return chat

    def append_message(
        self,
        tap_id: str,
        *,
        name: str,
        text: str,
        ts: str | None = None,
    ) -> None:
        chat = self._by_id.get(tap_id)
        if not chat:
            return
        stamp = ts or time.strftime("%H:%M")
        chat.messages.append({"name": name, "text": text, "ts": stamp})
        chat.updated_at = time.time()
        self.save()

    def remap_peer(self, tap_id: str, peer_id: str) -> None:
        chat = self._by_id.get(tap_id)
        if not chat or chat.peer_id == peer_id:
            return
        chat.peer_id = peer_id
        chat.updated_at = time.time()
        self.save()

    def remove(self, tap_id: str) -> None:
        if tap_id in self._by_id:
            del self._by_id[tap_id]
            self.save()

    def clear_messages(self, tap_id: str) -> None:
        chat = self._by_id.get(tap_id)
        if not chat:
            return
        chat.messages = []
        chat.updated_at = time.time()
        self.save()

    def tap_ids_for_server(
        self,
        link_id: str,
        *,
        host: str,
        port: int,
        participants: list[dict[str, Any]] | None = None,
    ) -> dict[tuple[str, str], str]:
        """Map (link_id, peer_id) -> tap_id for chats on this server."""
        by_name = {
            str(p.get("name", "")): str(p.get("client_id", ""))
            for p in (participants or [])
            if p.get("client_id")
        }
        result: dict[tuple[str, str], str] = {}
        for chat in self._by_id.values():
            if chat.link_host != host or chat.link_port != port:
                continue
            peer_id = chat.peer_id
            if participants and peer_id not in {str(p.get("client_id", "")) for p in participants}:
                alt = by_name.get(chat.peer_name)
                if alt:
                    peer_id = alt
                    self.remap_peer(chat.tap_id, peer_id)
            result[(link_id, peer_id)] = chat.tap_id
        return result


_store: ActiveTapChatStore | None = None


def get_active_tap_chat_store() -> ActiveTapChatStore:
    global _store
    if _store is None:
        _store = ActiveTapChatStore()
    return _store
