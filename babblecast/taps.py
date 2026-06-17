"""Local saved Tap reminders (client-side todo list per user)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from babblecast.paths import app_config_dir
from babblecast.protocol import new_id


def _taps_path(*, create: bool = False) -> Path:
    return app_config_dir(create=create) / "taps.json"


@dataclass
class SavedTap:
    save_id: str
    peer_id: str
    peer_name: str
    server_label: str
    reminder: str
    done: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        peer_id: str,
        peer_name: str,
        server_label: str,
        reminder: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> SavedTap:
        return cls(
            save_id=new_id(),
            peer_id=peer_id,
            peer_name=peer_name,
            server_label=server_label,
            reminder=reminder.strip(),
            messages=list(messages or []),
        )


class TapStore:
    def __init__(self) -> None:
        self._items: list[SavedTap] = []
        self.load()

    def load(self) -> None:
        path = _taps_path()
        if not path.exists():
            self._items = []
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._items = [
                SavedTap(
                    save_id=str(x.get("save_id", new_id())),
                    peer_id=str(x.get("peer_id", "")),
                    peer_name=str(x.get("peer_name", "")),
                    server_label=str(x.get("server_label", "")),
                    reminder=str(x.get("reminder", "")),
                    done=bool(x.get("done", False)),
                    messages=list(x.get("messages", [])),
                    created_at=float(x.get("created_at", time.time())),
                )
                for x in raw.get("taps", [])
            ]
        except (json.JSONDecodeError, TypeError, ValueError):
            self._items = []

    def save(self) -> None:
        path = _taps_path(create=True)
        payload = {"taps": [asdict(t) for t in self._items]}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def all_for_peer(self, peer_id: str) -> list[SavedTap]:
        return [t for t in self._items if t.peer_id == peer_id]

    def add(self, tap: SavedTap) -> None:
        self._items.append(tap)
        self.save()

    def mark_done(self, save_id: str, done: bool = True) -> None:
        for t in self._items:
            if t.save_id == save_id:
                t.done = done
                break
        self.save()

    def delete(self, save_id: str) -> None:
        self._items = [t for t in self._items if t.save_id != save_id]
        self.save()

    @property
    def items(self) -> list[SavedTap]:
        return list(self._items)


_store: TapStore | None = None


def get_tap_store() -> TapStore:
    global _store
    if _store is None:
        _store = TapStore()
    return _store
