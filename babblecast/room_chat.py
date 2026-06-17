"""Persisted room (main) chat history — tap/private chats stay ephemeral."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock, Timer
from typing import Any

from babblecast.paths import app_config_dir

_MAX_MESSAGES_PER_ROOM = 500
_SAVE_DEBOUNCE_SEC = 0.5


def room_chat_key(host: str, port: int, room_id: str) -> str:
    return f"{host.strip()}:{int(port)}:{room_id.strip()}"


@dataclass
class ChatLine:
    ts: float
    name: str
    text: str
    client_id: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChatLine:
        return cls(
            ts=float(raw.get("ts", time.time())),
            name=str(raw.get("name", "?")),
            text=str(raw.get("text", "")),
            client_id=str(raw.get("client_id", "")),
        )


@dataclass
class RoomChatHistory:
    key: str
    room_name: str = ""
    messages: list[ChatLine] = field(default_factory=list)


def _store_path(*, create: bool = False) -> Path:
    return app_config_dir(create=create) / "room_chat.json"


class RoomChatStore:
    """Client-side persistence for room-scoped main chat only."""

    def __init__(self) -> None:
        self._histories: dict[str, RoomChatHistory] = {}
        self._save_lock = Lock()
        self._save_timer: Timer | None = None
        self._dirty = False
        self.load()

    def load(self) -> None:
        path = _store_path()
        if not path.exists():
            self._histories = {}
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._histories = {}
            for key, block in raw.get("rooms", {}).items():
                msgs = [ChatLine.from_dict(m) for m in block.get("messages", [])]
                self._histories[key] = RoomChatHistory(
                    key=key,
                    room_name=str(block.get("room_name", "")),
                    messages=msgs[-_MAX_MESSAGES_PER_ROOM:],
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            self._histories = {}

    def _payload(self) -> dict[str, Any]:
        return {
            "rooms": {
                key: {
                    "room_name": hist.room_name,
                    "messages": [asdict(m) for m in hist.messages[-_MAX_MESSAGES_PER_ROOM:]],
                }
                for key, hist in self._histories.items()
            }
        }

    def _atomic_write(self) -> None:
        path = _store_path(create=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._payload(), indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _schedule_save(self) -> None:
        with self._save_lock:
            self._dirty = True
            if self._save_timer is not None:
                self._save_timer.cancel()
            timer = Timer(_SAVE_DEBOUNCE_SEC, self._flush_save)
            timer.daemon = True
            self._save_timer = timer
            timer.start()

    def _flush_save(self) -> None:
        with self._save_lock:
            if not self._dirty:
                return
            self._dirty = False
            self._save_timer = None
        self._atomic_write()

    def save(self) -> None:
        """Flush pending writes immediately (purge, shutdown)."""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            self._dirty = False
        self._atomic_write()

    def history(
        self,
        host: str,
        port: int,
        room_id: str,
        *,
        room_name: str = "",
    ) -> RoomChatHistory:
        key = room_chat_key(host, port, room_id)
        if key not in self._histories:
            self._histories[key] = RoomChatHistory(key=key, room_name=room_name)
        hist = self._histories[key]
        if room_name and not hist.room_name:
            hist.room_name = room_name
        return hist

    def append(
        self,
        host: str,
        port: int,
        room_id: str,
        name: str,
        text: str,
        *,
        client_id: str = "",
        ts: float | None = None,
        room_name: str = "",
    ) -> ChatLine:
        key = room_chat_key(host, port, room_id)
        hist = self.history(host, port, room_id, room_name=room_name)
        line = ChatLine(
            ts=ts if ts is not None else time.time(),
            name=name,
            text=text,
            client_id=client_id,
        )
        hist.messages.append(line)
        if len(hist.messages) > _MAX_MESSAGES_PER_ROOM:
            hist.messages = hist.messages[-_MAX_MESSAGES_PER_ROOM:]
        self._schedule_save()
        return line

    def lines(self, host: str, port: int, room_id: str) -> list[ChatLine]:
        key = room_chat_key(host, port, room_id)
        hist = self._histories.get(key)
        return list(hist.messages) if hist else []

    def purge(self, host: str, port: int, room_id: str) -> None:
        key = room_chat_key(host, port, room_id)
        if key in self._histories:
            del self._histories[key]
            self.save()


_store: RoomChatStore | None = None


def get_room_chat_store() -> RoomChatStore:
    global _store
    if _store is None:
        _store = RoomChatStore()
    return _store
