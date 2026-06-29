from __future__ import annotations

from babblecast.client.qt.midi.targets import TargetKind


def midi_to_bridge(kind: TargetKind, raw: int) -> float:
    v = max(0, min(127, int(raw)))
    if kind == "absolute":
        return v / 127.0 * 2.0
    raise ValueError(f"not absolute: {kind}")


def midi_to_gate_db(raw: int) -> float:
    v = max(0, min(127, int(raw)))
    return -80.0 + (v / 127.0) * 80.0


def midi_to_suppression(raw: int) -> float:
    v = max(0, min(127, int(raw)))
    return v / 127.0


def toggle_fire(raw: int) -> bool:
    return int(raw) > 0


def cc_toggle_fire(raw: int) -> bool:
    return int(raw) >= 64
