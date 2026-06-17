"""Noise gate and device label tests."""

from __future__ import annotations

import numpy as np

from babblecast.audio.codec import OpusCodec
from babblecast.audio.processing import NoiseGate, NoiseSuppressor, rms_db
from babblecast.constants import FRAME_BYTES, FRAME_SAMPLES


def test_rms_db_silence() -> None:
    samples = np.zeros(960, dtype=np.int16)
    assert rms_db(samples) <= -100


def test_noise_gate_closes_quiet_signal() -> None:
    gate = NoiseGate(threshold_db=-20.0)
    quiet = (np.random.randn(960) * 10).astype(np.int16)
    out, _level = gate.process(quiet)
    assert float(np.max(np.abs(out))) < float(np.max(np.abs(quiet)))


def test_noise_gate_opens_loud_signal() -> None:
    gate = NoiseGate(threshold_db=-40.0)
    loud = (np.random.randn(960) * 8000).astype(np.int16)
    _, level = gate.process(loud)
    assert level > 0.1


def test_noise_suppressor_skips_short_frame() -> None:
    suppressor = NoiseSuppressor(strength=0.8)
    frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
    out = suppressor.process(frame)
    assert out.shape == frame.shape


def test_opus_codec_pads_short_pcm() -> None:
    codec = OpusCodec()
    short = b"\x00" * (FRAME_BYTES // 2)
    packet = codec.encode(short)
    assert packet
    pcm = codec.decode(packet)
    assert len(pcm) == FRAME_BYTES


def test_opus_codec_empty_packet_returns_silence() -> None:
    codec = OpusCodec()
    assert len(codec.decode(b"")) == FRAME_BYTES
