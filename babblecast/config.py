"""User preferences persisted via save API only."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


from babblecast.paths import app_config_dir


def _config_dir(*, create: bool = False) -> Path:
    return app_config_dir(create=create)


def _config_path() -> Path:
    return _config_dir() / "settings.json"


@dataclass
class UserSettings:
    display_name: str = ""
    input_device: str | None = None
    output_device: str | None = None
    gate_threshold_db: float = -40.0
    noise_suppression: float = 0.5
    input_volume: float = 1.0
    output_volume: float = 1.0
    ptt_key: str = "space"
    last_server_host: str = "127.0.0.1"
    last_server_port: int = 8765
    hosted_server_name: str = ""
    per_user_volumes: dict[str, float] = field(default_factory=dict)
    per_user_muted: dict[str, bool] = field(default_factory=dict)
    window_geometry: list[int] | None = None
    ui_panel_expanded: bool = False
    ui_self_audio_expanded: bool = False
    skip_disconnect_confirm: bool = False

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
                input_volume=float(raw.get("input_volume", 1.0)),
                output_volume=float(raw.get("output_volume", 1.0)),
                ptt_key=str(raw.get("ptt_key", "space")),
                last_server_host=str(raw.get("last_server_host", "127.0.0.1")),
                last_server_port=int(raw.get("last_server_port", 8765)),
                hosted_server_name=str(raw.get("hosted_server_name", "")),
                per_user_volumes=dict(raw.get("per_user_volumes", {})),
                per_user_muted={k: bool(v) for k, v in raw.get("per_user_muted", {}).items()},
                window_geometry=raw.get("window_geometry"),
                ui_panel_expanded=bool(raw.get("ui_panel_expanded", False)),
                ui_self_audio_expanded=bool(raw.get("ui_self_audio_expanded", False)),
                skip_disconnect_confirm=bool(raw.get("skip_disconnect_confirm", False)),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self) -> None:
        path = _config_dir(create=True) / "settings.json"
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
