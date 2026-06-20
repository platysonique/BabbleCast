from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class MidiMap:
    midi_type: str
    midi_channel: int
    midi_number: int
    target_id: str
    param: str
    ctrl_idx: int = 0
    port: int = 0
    port_name: str = ""


def _ch_matches(m: MidiMap, channel: int) -> bool:
    return m.midi_channel == 0 or m.midi_channel == channel


def _ctrl_matches(m: MidiMap, ctrl_idx: int, port: int) -> bool:
    if m.ctrl_idx < 0 or m.port < 0:
        return True
    return m.ctrl_idx == ctrl_idx and m.port == port


def _conflicts(m: MidiMap, midi_type: str, ch: int, num: int) -> bool:
    if m.midi_type != midi_type or m.midi_number != num:
        return False
    if m.midi_channel == 0 or ch == 0:
        return True
    return m.midi_channel == ch


class BindingEngine:
    def __init__(self) -> None:
        self._maps: list[MidiMap] = []
        self._setters: dict[str, dict[str, Callable[[int], None]]] = {}

    def register_target(self, target_id: str, param: str, setter: Callable[[int], None]) -> None:
        self._setters.setdefault(target_id, {})[param] = setter

    def unregister_target(self, target_id: str) -> None:
        self._setters.pop(target_id, None)

    def map_midi(
        self,
        midi_type: str,
        midi_channel: int,
        midi_number: int,
        target_id: str,
        param: str,
        *,
        ctrl_idx: int = 0,
        port: int = 0,
        port_name: str = "",
    ) -> None:
        self._maps = [m for m in self._maps if not _conflicts(m, midi_type, midi_channel, midi_number)]
        self._maps.append(
            MidiMap(midi_type, midi_channel, midi_number, target_id, param, ctrl_idx, port, port_name)
        )

    def unmap_target(self, target_id: str, param: str | None = None) -> None:
        if param is None:
            self._maps = [m for m in self._maps if m.target_id != target_id]
        else:
            self._maps = [m for m in self._maps if not (m.target_id == target_id and m.param == param)]

    def get_map(self, target_id: str, param: str) -> MidiMap | None:
        for m in self._maps:
            if m.target_id == target_id and m.param == param:
                return m
        return None

    def is_mapped(self, target_id: str, param: str) -> bool:
        return self.get_map(target_id, param) is not None

    def all_maps(self) -> list[MidiMap]:
        return list(self._maps)

    def prune_targets(self, prefix: str) -> None:
        self._maps = [m for m in self._maps if not m.target_id.startswith(prefix)]
        for tid in list(self._setters):
            if tid.startswith(prefix):
                self._setters.pop(tid, None)

    def on_midi_cc(self, cc: int, value: int, channel: int, ctrl_idx: int = 0, port: int = 0) -> None:
        for m in self._maps:
            if m.midi_type != "cc" or m.midi_number != cc:
                continue
            if not _ch_matches(m, channel) or not _ctrl_matches(m, ctrl_idx, port):
                continue
            setters = self._setters.get(m.target_id, {})
            if value == 0 and setters.get("release"):
                setters["release"](0)
                continue
            if setters.get("value") and m.param in ("value", "ptt"):
                setters["value"](value)
            elif setters.get("trigger") and value > 0 and m.param == "trigger":
                setters["trigger"](value)

    def on_midi_note(self, note: int, velocity: int, channel: int, ctrl_idx: int = 0, port: int = 0) -> None:
        if velocity == 0:
            self.on_midi_note_off(note, channel, ctrl_idx=ctrl_idx, port=port)
            return
        for m in self._maps:
            if m.midi_type != "note" or m.midi_number != note:
                continue
            if not _ch_matches(m, channel) or not _ctrl_matches(m, ctrl_idx, port):
                continue
            setters = self._setters.get(m.target_id, {})
            if setters.get("trigger") and m.param == "trigger":
                setters["trigger"](velocity)
            elif setters.get("value") and m.param in ("value", "ptt"):
                setters["value"](velocity)

    def on_midi_note_off(self, note: int, channel: int, ctrl_idx: int = 0, port: int = 0) -> None:
        for m in self._maps:
            if m.midi_type != "note" or m.midi_number != note:
                continue
            if not _ch_matches(m, channel) or not _ctrl_matches(m, ctrl_idx, port):
                continue
            release = self._setters.get(m.target_id, {}).get("release")
            if release and m.param in ("ptt", "release"):
                release(0)

    def serialize_maps(self) -> list[dict]:
        return [
            {
                "type": m.midi_type,
                "ch": m.midi_channel,
                "num": m.midi_number,
                "tgt": m.target_id,
                "param": m.param,
                "ctrl_idx": m.ctrl_idx,
                "port": m.port,
                "port_name": m.port_name,
            }
            for m in self._maps
        ]

    def load_maps(self, rows: list[dict]) -> None:
        self._maps.clear()
        for row in rows:
            self._maps.append(
                MidiMap(
                    str(row["type"]),
                    int(row.get("ch", 0)),
                    int(row["num"]),
                    str(row["tgt"]),
                    str(row.get("param", "value")),
                    int(row.get("ctrl_idx", 0)),
                    int(row.get("port", 0)),
                    str(row.get("port_name", "")),
                )
            )

    def clear_maps(self) -> None:
        self._maps.clear()
