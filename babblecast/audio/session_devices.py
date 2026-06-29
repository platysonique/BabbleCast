"""Map OS session audio defaults to PortAudio device indices (desktop)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SYSTEM_DEFAULT_KEY = "@system"
NAME_KEY_PREFIX = "name:"

_LEGACY_VIRTUAL_NAMES = frozenset({"default", "pipewire", "pulse", "sysdefault"})

_ALSA_PLUGIN_JUNK = frozenset({
    "lavrate",
    "samplerate",
    "speexrate",
    "speex",
    "upmix",
    "vdownmix",
    "dmix",
    "front",
    "surround40",
    "surround51",
    "surround71",
    "hdmi",
})

_HW_RE = re.compile(r"\(hw:\d+,\d+\)")
SESSION_ROUTE_NAMES = frozenset({"pipewire", "pulse", "default"})


def normalize_device_key(key: str | None, *, output: bool = True) -> str | None:
    """Convert legacy PortAudio index keys to stable session/name keys."""
    if key is None or key == "":
        return SYSTEM_DEFAULT_KEY
    if key == SYSTEM_DEFAULT_KEY:
        return key
    if key.startswith(NAME_KEY_PREFIX):
        return key
    if ":" in key:
        _idx, name = key.split(":", 1)
        if name in _LEGACY_VIRTUAL_NAMES:
            return SYSTEM_DEFAULT_KEY
        return f"{NAME_KEY_PREFIX}{name}"
    if key in _LEGACY_VIRTUAL_NAMES:
        return SYSTEM_DEFAULT_KEY
    return f"{NAME_KEY_PREFIX}{key}"


def migrate_settings_devices(
    input_device: str | None,
    output_device: str | None,
) -> tuple[str | None, str | None]:
    return (
        normalize_device_key(input_device, output=False),
        normalize_device_key(output_device, output=True),
    )


def is_alsa_plugin_junk(name: str) -> bool:
    lower = name.strip().lower()
    if lower in _ALSA_PLUGIN_JUNK:
        return True
    if lower in _LEGACY_VIRTUAL_NAMES:
        return True
    return False


def is_physical_portaudio_name(name: str) -> bool:
    return bool(_HW_RE.search(name))


def friendly_name_for_portaudio_device(name: str) -> str:
    if "analog" in name.lower():
        return "Built-in analog (headphones / speakers)"
    if "hdmi" in name.lower():
        return name.replace("HDA Intel PCH: ", "").replace(" (hw:", " —").split("—")[0].strip()
    if "usb" in name.lower():
        return name.split("(hw:")[0].strip()
    return name.split("(hw:")[0].strip() or name


@dataclass(frozen=True)
class SessionEndpoint:
    endpoint_id: str
    description: str


def _run_text(cmd: list[str], timeout: float = 2.5) -> str:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def query_linux_session_output() -> SessionEndpoint | None:
    if sys.platform != "linux":
        return None
    if not shutil.which("pactl"):
        return None
    sink_id = _run_text(["pactl", "get-default-sink"])
    if not sink_id:
        return None
    listing = _run_text(["pactl", "list", "sinks"])
    description = sink_id
    if listing:
        block = ""
        in_block = False
        for line in listing.splitlines():
            if line.startswith("Sink #"):
                in_block = False
                block = ""
            if f"Name: {sink_id}" in line:
                in_block = True
            if in_block:
                block += line + "\n"
                if line.startswith("Description:"):
                    description = line.split(":", 1)[1].strip()
        if description == sink_id and block:
            m = re.search(r"Description:\s*(.+)", block)
            if m:
                description = m.group(1).strip()
    return SessionEndpoint(endpoint_id=sink_id, description=description)


def query_linux_session_input() -> SessionEndpoint | None:
    if sys.platform != "linux":
        return None
    if not shutil.which("pactl"):
        return None
    source_id = _run_text(["pactl", "get-default-source"])
    if not source_id:
        return None
    listing = _run_text(["pactl", "list", "sources"])
    description = source_id
    if listing:
        in_block = False
        block = ""
        for line in listing.splitlines():
            if line.startswith("Source #"):
                in_block = False
                block = ""
            if f"Name: {source_id}" in line:
                in_block = True
            if in_block:
                block += line + "\n"
                if line.startswith("Description:"):
                    description = line.split(":", 1)[1].strip()
        if description == source_id and block:
            m = re.search(r"Description:\s*(.+)", block)
            if m:
                description = m.group(1).strip()
    return SessionEndpoint(endpoint_id=source_id, description=description)


def _tokenize(value: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", value.lower()) if len(t) > 2}


def _score_device_for_session(
    device_name: str,
    session: SessionEndpoint | None,
    *,
    output: bool,
) -> int:
    if session is None:
        return 0
    score = 0
    dev_lower = device_name.lower()
    sink_lower = session.endpoint_id.lower()
    desc_lower = session.description.lower()

    if "analog" in sink_lower and "analog" in dev_lower:
        score += 100
    if "hdmi" in sink_lower and "hdmi" in dev_lower:
        score += 100
    if output and "hdmi" in dev_lower and "analog" in sink_lower:
        score -= 120
    if "usb" in sink_lower and "usb" in dev_lower:
        score += 100
    if "bluetooth" in sink_lower and "blue" in dev_lower:
        score += 100

    shared = _tokenize(device_name) & (_tokenize(session.endpoint_id) | _tokenize(session.description))
    score += min(len(shared) * 10, 40)

    if output and "monitor" in dev_lower:
        score -= 50
    if not output and "monitor" in sink_lower and "monitor" in dev_lower:
        score += 30
    if not output and "monitor" in dev_lower and "monitor" not in sink_lower:
        score -= 50

    if is_physical_portaudio_name(device_name):
        score += 5

    if "headset" in desc_lower and "headset" in dev_lower:
        score += 20
    if "microphone" in desc_lower and "mic" in dev_lower:
        score += 15
    if "microphone" in desc_lower and "microphone" in dev_lower:
        score += 15

    # Built-in laptop path: session says "Built-in Audio Analog Stereo"
    if "built-in" in desc_lower and "analog" in dev_lower:
        score += 80

    return score


def session_matches_device_name(device_name: str, session: SessionEndpoint | None) -> bool:
    """True when the OS default source is the same endpoint as *device_name*."""
    if not device_name or session is None:
        return False
    return _score_device_for_session(device_name, session, output=False) >= 50


def resolve_session_device_index(
    candidates: list[tuple[int, str]],
    *,
    output: bool,
) -> int | None:
    """Pick the PortAudio index that best matches the OS default sink/source."""
    if not candidates:
        return None
    session = (
        query_linux_session_output() if output else query_linux_session_input()
    )
    if session is None:
        physical = [(i, n) for i, n in candidates if is_physical_portaudio_name(n)]
        if physical:
            return physical[0][0]
        return candidates[0][0]

    ranked = sorted(
        candidates,
        key=lambda item: (
            -_score_device_for_session(item[1], session, output=output),
            item[0],
        ),
    )
    best_score = _score_device_for_session(ranked[0][1], session, output=output)
    if best_score <= 0:
        physical = [(i, n) for i, n in candidates if is_physical_portaudio_name(n)]
        if physical:
            return physical[0][0]
    logger.info(
        "Session %s resolved to PortAudio device %s (%s) for %s",
        "output" if output else "input",
        ranked[0][0],
        ranked[0][1],
        session.description,
    )
    return ranked[0][0]


def device_name_from_key(key: str | None) -> str | None:
    if not key or key == SYSTEM_DEFAULT_KEY:
        return None
    if key.startswith(NAME_KEY_PREFIX):
        return key[len(NAME_KEY_PREFIX) :]
    if ":" in key:
        return key.split(":", 1)[1]
    return key
