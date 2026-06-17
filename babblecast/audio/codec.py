"""Opus codec helpers — never pass invalid buffers to native libopus."""

from __future__ import annotations

import logging

import opuslib
import opuslib.exceptions

from babblecast.constants import CHANNELS, FRAME_BYTES, FRAME_SAMPLES, SAMPLE_RATE

logger = logging.getLogger(__name__)

# Opus needs a real packet; shorter payloads have caused silk/resampler aborts on some builds.
_MIN_OPUS_PACKET_BYTES = 4
_MAX_OPUS_PACKET_BYTES = 1275  # RFC 6716 practical upper bound for one frame


def _normalize_pcm(pcm: bytes) -> bytes:
    if len(pcm) < FRAME_BYTES:
        return pcm.ljust(FRAME_BYTES, b"\x00")
    if len(pcm) > FRAME_BYTES:
        return pcm[:FRAME_BYTES]
    return pcm


class OpusCodec:
    def __init__(self) -> None:
        self._encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
        self._decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
        self._encoder.bitrate = 64000

    def encode(self, pcm: bytes) -> bytes | None:
        if not pcm:
            return None
        pcm = _normalize_pcm(pcm)
        if len(pcm) != FRAME_BYTES:
            return None
        try:
            return self._encoder.encode(pcm, FRAME_SAMPLES)
        except opuslib.exceptions.OpusError:
            logger.debug("Opus encode rejected frame", exc_info=True)
            return None

    def decode(self, packet: bytes) -> bytes:
        if not packet or len(packet) < _MIN_OPUS_PACKET_BYTES or len(packet) > _MAX_OPUS_PACKET_BYTES:
            return b"\x00" * FRAME_BYTES
        try:
            pcm = self._decoder.decode(packet, FRAME_SAMPLES)
        except opuslib.exceptions.OpusError:
            logger.debug("Opus decode rejected packet len=%s", len(packet), exc_info=True)
            return b"\x00" * FRAME_BYTES
        return _normalize_pcm(pcm)

    def decode_plc(self) -> bytes:
        """Packet-loss concealment — call when a frame was expected but missing."""
        try:
            pcm = self._decoder.decode(b"", FRAME_SAMPLES)
            if pcm and len(pcm) >= FRAME_BYTES:
                return _normalize_pcm(pcm)
        except opuslib.exceptions.OpusError:
            logger.debug("Opus PLC failed", exc_info=True)
        return b"\x00" * FRAME_BYTES
