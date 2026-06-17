"""Opus codec helpers."""

from __future__ import annotations

import opuslib

from babblecast.constants import CHANNELS, FRAME_SAMPLES, SAMPLE_RATE


class OpusCodec:
    def __init__(self) -> None:
        self._encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
        self._decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
        self._encoder.bitrate = 64000

    def encode(self, pcm: bytes) -> bytes:
        return self._encoder.encode(pcm, FRAME_SAMPLES)

    def decode(self, packet: bytes) -> bytes:
        return self._decoder.decode(packet, FRAME_SAMPLES)
