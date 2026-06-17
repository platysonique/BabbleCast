"""User preferences persisted via save API only."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = Path(base) / "babblecast"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path() -> Path:
    return _config_dir() / "settings.json"


@dataclass
class UserSettings:
    display_name: str = ""
    input_device: str | None = None
    output_device: str | None = None
    gate_threshold_db: float = -40.0
    noise_suppression: float = 0.5
    output_volume: float = 1.0
    ptt_key: str = "space"
    last_server_host: str = "127.0.0.1"
    last_server_port: int = 8765
    per_user_volumes: dict[str, float] = field(default_factory=dict)
    per_user_muted: dict[str, bool] = field(default_factory=dict)
    window_geometry: list[int] | None = None

    @classmethod
    def load(cls) -> UserSettings:
        path = _config_path()
        if not path.exists():
            return cls()
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                display_name=str(raw.get("display_name", "")),
                input_device=raw.get("input_device"),
                output_device=raw.get("output_device"),
                gate_threshold_db=float(raw.get("gate_threshold_db", -40.0)),
                noise_suppression=float(raw.get("noise_suppression", 0.5)),
                output_volume=float(raw.get("output_volume", 1.0)),
                ptt_key=str(raw.get("ptt_key", "space")),
                last_server_host=str(raw.get("last_server_host", "127.0.0.1")),
                last_server_port=int(raw.get("last_server_port", 8765)),
                per_user_volumes=dict(raw.get("per_user_volumes", {})),
                per_user_muted={k: bool(v) for k, v in raw.get("per_user_muted", {}).items()},
                window_geometry=raw.get("window_geometry"),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self) -> None:
        path = _config_path()
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


_settings: UserSettings | None = None


def get_settings() -> UserSettings:
    global _settings
    if _settings is None:
        _settings = UserSettings.load()
    return _settings


def save_settings(settings: UserSettings | None = None) -> None:
    global _settings
    target = settings if settings is not None else _settings
    if target is None:
        target = UserSettings.load()
    target.save()
    _settings = target
