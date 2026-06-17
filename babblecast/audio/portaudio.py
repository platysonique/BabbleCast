"""Open PortAudio streams with device fallback (Linux ALSA/PipeWire)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import sounddevice as sd

from babblecast.audio.devices import list_input_devices, list_output_devices

logger = logging.getLogger(__name__)

_HOST_API_PREFERENCE = ("pipewire", "pulse", "alsa", "jack")


def _host_rank(host_api: str) -> int:
    lower = host_api.lower()
    for i, name in enumerate(_HOST_API_PREFERENCE):
        if name in lower:
            return i
    return len(_HOST_API_PREFERENCE)


def _ordered_indices(
    devices,
    preferred_key: str | None,
    *,
    default_attr: str,
) -> Iterator[int]:
    seen: set[int] = set()
    if preferred_key:
        for d in devices:
            if d.storage_key == preferred_key or preferred_key.endswith(d.name):
                if d.index not in seen:
                    seen.add(d.index)
                    yield d.index
    defaults = [d for d in devices if getattr(d, default_attr)]
    defaults.sort(key=lambda d: _host_rank(d.host_api))
    for d in defaults:
        if d.index not in seen:
            seen.add(d.index)
            yield d.index
    ranked = sorted(devices, key=lambda d: (_host_rank(d.host_api), d.index))
    for d in ranked:
        if d.index not in seen:
            seen.add(d.index)
            yield d.index


def iter_input_device_indices(preferred_key: str | None) -> Iterator[int]:
    yield from _ordered_indices(list_input_devices(), preferred_key, default_attr="is_default_input")


def iter_output_device_indices(preferred_key: str | None) -> Iterator[int]:
    yield from _ordered_indices(list_output_devices(), preferred_key, default_attr="is_default_output")
