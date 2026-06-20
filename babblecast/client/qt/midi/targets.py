from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TargetKind = Literal["absolute", "toggle", "momentary", "ptt"]
TargetScope = Literal["global", "link", "peer"]

_PEER_ACTIONS = ("volume", "listen_mute", "send_tap")
_LINK_ACTIONS = ("listen_mute", "mic_mute")


@dataclass(frozen=True)
class MidiTarget:
    target_id: str
    label: str
    kind: TargetKind
    scope: TargetScope
    link_id: str | None = None
    composite: str | None = None
    peer_name: str | None = None
    link_label: str | None = None


def global_target(action: str) -> str:
    return f"global.{action}"


def link_target(link_id: str, action: str) -> str:
    return f"link.{link_id}.{action}"


def peer_target(composite: str, action: str) -> str:
    return f"peer.{composite}.{action}"


def parse_peer_target(target_id: str) -> tuple[str, str] | None:
    if not target_id.startswith("peer."):
        return None
    body = target_id[5:]
    for action in _PEER_ACTIONS:
        suffix = f".{action}"
        if body.endswith(suffix):
            return body[: -len(suffix)], action
    return None


def parse_link_target(target_id: str) -> tuple[str, str] | None:
    if not target_id.startswith("link."):
        return None
    body = target_id[5:]
    for action in _LINK_ACTIONS:
        suffix = f".{action}"
        if body.endswith(suffix):
            return body[: -len(suffix)], action
    return None


def label_for_target_id(target_id: str, meta: dict | None = None) -> str:
    meta = meta or {}
    if target_id == global_target("mic_volume"):
        return "Mic input volume"
    if target_id == global_target("master_volume"):
        return "Master volume"
    if target_id == global_target("gate"):
        return "Noise gate"
    if target_id == global_target("suppression"):
        return "Noise suppression"
    if target_id == global_target("mute"):
        return "Global mic mute"
    if target_id == global_target("ptt"):
        return "Push-to-talk (while muted)"
    parsed = parse_link_target(target_id)
    if parsed:
        lid, action = parsed
        name = meta.get("link_label") or lid[:8]
        if action == "listen_mute":
            return f"{name} — Listen mute"
        return f"{name} — Mic mute"
    parsed = parse_peer_target(target_id)
    if parsed:
        _composite, action = parsed
        name = meta.get("peer_name") or "Peer"
        server = meta.get("link_label")
        prefix = f"{name} ({server})" if server else name
        if action == "volume":
            return f"{prefix} — Volume"
        if action == "listen_mute":
            return f"{prefix} — Listen mute"
        return f"{prefix} — Send tap"
    return target_id
