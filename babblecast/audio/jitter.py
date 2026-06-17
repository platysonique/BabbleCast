"""Per-sender UDP voice jitter / sequence tracking."""

from __future__ import annotations

from babblecast.constants import FRAME_BYTES

# Max consecutive PLC frames before giving up on a gap burst.
_MAX_PLC_BURST = 6


def _seq_after(seq: int) -> int:
    return (seq + 1) & 0xFFFFFFFF


def _seq_before(seq: int) -> int:
    return (seq - 1) & 0xFFFFFFFF


def _seq_newer(a: int, b: int) -> bool:
    """True if a is newer than b (handles 32-bit wrap)."""
    return ((a - b) & 0xFFFFFFFF) < 0x80000000


class VoiceJitterBuffer:
    """Track sequence numbers; emit Opus payloads or None for PLC."""

    def __init__(self) -> None:
        self._last_seq: int | None = None

    def reset(self) -> None:
        self._last_seq = None

    def push(self, sequence: int, opus_payload: bytes) -> list[bytes | None]:
        if not opus_payload:
            return []
        if self._last_seq is None:
            self._last_seq = sequence
            return [opus_payload]

        if sequence == self._last_seq:
            return []  # duplicate

        if not _seq_newer(sequence, self._last_seq):
            return []  # late / stale

        out: list[bytes | None] = []
        expected = _seq_after(self._last_seq)
        plc_count = 0
        while expected != sequence and plc_count < _MAX_PLC_BURST:
            out.append(None)
            expected = _seq_after(expected)
            plc_count += 1
        if expected != sequence:
            # Large gap — jump to new sequence rather than PLC storm
            self._last_seq = sequence
            return [opus_payload]

        out.append(opus_payload)
        self._last_seq = sequence
        return out


def silence_frame() -> bytes:
    return b"\x00" * FRAME_BYTES
