"""Microphone open candidates — session routes, hardware, and native-rate fallback."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import sounddevice as sd

from babblecast.audio.devices import list_raw_input_candidates, list_session_input_routes
from babblecast.audio.session_devices import (
    SESSION_ROUTE_NAMES,
    SYSTEM_DEFAULT_KEY,
    device_name_from_key,
    normalize_device_key,
    query_linux_session_input,
    resolve_session_device_index,
    session_matches_device_name,
)
from babblecast.constants import SAMPLE_RATE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MicOpenCandidate:
    device_index: int
    sample_rate: int
    route_kind: str


def device_supports_input_rate(device_index: int, sample_rate: int) -> bool:
    try:
        sd.check_input_settings(
            device=device_index,
            channels=1,
            samplerate=sample_rate,
            dtype="float32",
        )
        return True
    except Exception:
        return False


def native_input_sample_rate(device_index: int) -> int:
    try:
        return int(float(sd.query_devices(device_index)["default_samplerate"]))
    except Exception:
        return SAMPLE_RATE


def _session_virtual_routes(candidates: list[tuple[int, str]]) -> list[tuple[int, str]]:
    routes: list[tuple[int, str]] = []
    by_name = {name.lower(): idx for idx, name in candidates}
    for name in SESSION_ROUTE_NAMES:
        idx = by_name.get(name)
        if idx is not None and device_supports_input_rate(idx, SAMPLE_RATE):
            routes.append((idx, name))
    return routes


def _session_virtual_routes_from_devices() -> list[tuple[int, str]]:
    return _session_virtual_routes(list_session_input_routes())


def _hardware_candidates(device_name: str | None) -> list[tuple[int, str]]:
    if not device_name:
        return []
    matches: list[tuple[int, str]] = []
    for idx, name in list_raw_input_candidates():
        if name == device_name or device_name in name or name in device_name:
            matches.append((idx, name))
    return matches


def iter_mic_open_candidates(device_key: str | None) -> Iterator[MicOpenCandidate]:
    """Yield mic open strategies in priority order for the requested device key."""
    key = normalize_device_key(device_key, output=False)
    candidates = list_raw_input_candidates()
    session = query_linux_session_input()
    virtual = _session_virtual_routes_from_devices()
    seen: set[tuple[int, int]] = set()

    def _offer(device_index: int, sample_rate: int, route_kind: str) -> MicOpenCandidate | None:
        token = (device_index, sample_rate)
        if token in seen:
            return None
        seen.add(token)
        return MicOpenCandidate(device_index, sample_rate, route_kind)

    if key == SYSTEM_DEFAULT_KEY:
        for idx, name in virtual:
            cand = _offer(idx, SAMPLE_RATE, f"session:{name}")
            if cand:
                yield cand
        resolved = resolve_session_device_index(candidates, output=False)
        if resolved is not None:
            if device_supports_input_rate(resolved, SAMPLE_RATE):
                cand = _offer(resolved, SAMPLE_RATE, "hardware")
            else:
                cand = _offer(
                    resolved,
                    native_input_sample_rate(resolved),
                    "hardware-resampled",
                )
            if cand:
                yield cand
        for idx, name in candidates:
            if device_supports_input_rate(idx, SAMPLE_RATE):
                cand = _offer(idx, SAMPLE_RATE, "fallback")
                if cand:
                    yield cand
        return

    target_name = device_name_from_key(key)
    hw_matches = _hardware_candidates(target_name)
    use_session = session_matches_device_name(target_name or "", session)

    if use_session:
        for idx, name in virtual:
            cand = _offer(idx, SAMPLE_RATE, f"session:{name}")
            if cand:
                yield cand

    for idx, name in hw_matches:
        if device_supports_input_rate(idx, SAMPLE_RATE):
            cand = _offer(idx, SAMPLE_RATE, "hardware")
            if cand:
                yield cand
        else:
            native = native_input_sample_rate(idx)
            if native > 0:
                logger.info(
                    "Mic %s (%s) will capture at %s Hz and resample to %s Hz",
                    name,
                    idx,
                    native,
                    SAMPLE_RATE,
                )
                cand = _offer(idx, native, "hardware-resampled")
                if cand:
                    yield cand

    if not hw_matches and target_name:
        logger.warning("No PortAudio input matched requested mic: %s", target_name)
