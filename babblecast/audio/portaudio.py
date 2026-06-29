"""Open PortAudio streams with device fallback (Linux ALSA/PipeWire)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from babblecast.audio.devices import (
    list_raw_input_candidates,
    list_raw_output_candidates,
    resolve_input_device,
    resolve_output_device,
)
from babblecast.audio.session_devices import (
    SYSTEM_DEFAULT_KEY,
    device_name_from_key,
    normalize_device_key,
)

logger = logging.getLogger(__name__)


def _ordered_indices(
    preferred_key: str | None,
    *,
    output: bool,
) -> Iterator[int]:
    seen: set[int] = set()
    key = normalize_device_key(preferred_key, output=output)

    resolved = (
        resolve_output_device(key) if output else resolve_input_device(key)
    )
    if resolved is not None and resolved not in seen:
        seen.add(resolved)
        yield resolved

    if key != SYSTEM_DEFAULT_KEY:
        name = device_name_from_key(key)
        candidates = (
            list_raw_output_candidates() if output else list_raw_input_candidates()
        )
        if name:
            for idx, dev_name in candidates:
                if dev_name == name and idx not in seen:
                    seen.add(idx)
                    yield idx

    session_fallback = (
        resolve_output_device(SYSTEM_DEFAULT_KEY)
        if output
        else resolve_input_device(SYSTEM_DEFAULT_KEY)
    )
    if session_fallback is not None and session_fallback not in seen:
        seen.add(session_fallback)
        yield session_fallback

    candidates = (
        list_raw_output_candidates() if output else list_raw_input_candidates()
    )
    for idx, _name in sorted(candidates, key=lambda item: item[0]):
        if idx not in seen:
            seen.add(idx)
            yield idx


def iter_input_device_indices(preferred_key: str | None) -> Iterator[int]:
    yield from _ordered_indices(preferred_key, output=False)


def iter_output_device_indices(preferred_key: str | None) -> Iterator[int]:
    yield from _ordered_indices(preferred_key, output=True)
