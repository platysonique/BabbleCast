"""Shared constants for BabbleCast protocol and audio."""

SERVICE_TYPE = "_babblecast._tcp.local."
LOCAL_DOMAIN = "babblecast.local"

DEFAULT_WS_PORT = 9513
DEFAULT_UDP_PORT = 9514
DISCOVERY_BEACON_PORT = 9515
SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_SAMPLES = 960  # 20 ms @ 48 kHz
FRAME_BYTES = FRAME_SAMPLES * 2  # int16 mono
FRAME_DURATION_SEC = FRAME_SAMPLES / SAMPLE_RATE

# Voice playback — keep queues shallow for LAN (Jamulus-style low latency).
VOICE_PLAYBACK_QUEUE_MAX = 3

# WebSocket keepalive — tolerant of Wi‑Fi / mesh hiccups.
WS_PING_INTERVAL_SEC = 30
WS_PING_TIMEOUT_SEC = 60

# Cap control-plane voice-level updates (mic meter → server presence).
VOICE_LEVEL_WS_MIN_INTERVAL_SEC = 0.1

UDP_MAGIC = b"BBC\x01"
MAX_CHAT_LEN = 4096
MAX_NAME_LEN = 64
MAX_ROOM_NAME_LEN = 128
MAX_TAP_REMINDER_LEN = 512
DISCOVERY_STALE_SEC = 30

# UI feedback colors (Tokyo Night–aligned)
UI_ACTIVE_GREEN = "#9ece6a"
UI_MUTED_RED = "#f7768e"
UI_MUTE_ORANGE = "#e0af68"
UI_SUNFLOWER = "#ffda03"


def composite_participant_key(link_id: str, client_id: str) -> str:
    """Unique speaker key when bridging multiple servers."""
    return f"{link_id}:{client_id}"


def babblecast_subnet_prefix() -> str:
    """Legacy alias — use ``babblecast.address.babblecast_prefix()``."""
    from babblecast.address import babblecast_prefix

    return babblecast_prefix()


def babblecast_subnet_example_host(last_octet: int = 10, domain: int = 9) -> str:
    """Example LAN IP for UI hints."""
    return f"192.168.{domain}.{last_octet}"
