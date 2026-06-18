"""Shared constants for BabbleCast protocol and audio."""

SERVICE_TYPE = "_babblecast._tcp.local."
LOCAL_DOMAIN = "babblecast.local"

# BabbleCast LAN — each machine picks its address in this range (e.g. 11.2.9.10).
# Self-connect on the same machine still uses 127.0.0.1.
BABBLECAST_SUBNET = (11, 2, 9)

DEFAULT_WS_PORT = 9513
DEFAULT_UDP_PORT = 9514
SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_SAMPLES = 960  # 20 ms @ 48 kHz
FRAME_BYTES = FRAME_SAMPLES * 2  # int16 mono

UDP_MAGIC = b"BBC\x01"
MAX_CHAT_LEN = 4096
MAX_NAME_LEN = 64
MAX_ROOM_NAME_LEN = 128
MAX_TAP_REMINDER_LEN = 512
DISCOVERY_STALE_SEC = 30


def composite_participant_key(link_id: str, client_id: str) -> str:
    """Unique speaker key when bridging multiple servers."""
    return f"{link_id}:{client_id}"


def babblecast_subnet_prefix() -> str:
    """Dotted prefix for the BabbleCast subnet, e.g. ``11.2.9``."""
    return ".".join(str(o) for o in BABBLECAST_SUBNET)


def babblecast_subnet_example_host(last_octet: int = 10) -> str:
    return f"{babblecast_subnet_prefix()}.{last_octet}"
