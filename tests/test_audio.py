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
    quiet = (np.random.randn(FRAME_SAMPLES) * 10).astype(np.int16)
    out = quiet
    for _ in range(12):
        out, _level = gate.process(quiet)
    assert float(np.max(np.abs(out))) < float(np.max(np.abs(quiet)) * 0.2)


def test_noise_gate_opens_loud_signal() -> None:
    gate = NoiseGate(threshold_db=-40.0)
    loud = (np.random.randn(FRAME_SAMPLES) * 8000).astype(np.int16)
    out = loud
    for _ in range(6):
        out, level = gate.process(loud)
    assert gate.is_open()
    assert float(np.max(np.abs(out))) > float(np.max(np.abs(loud)) * 0.5)


def test_noise_gate_threshold_affects_open_state() -> None:
    loud = (np.random.randn(FRAME_SAMPLES) * 6000).astype(np.int16)
    strict = NoiseGate(threshold_db=0.0)
    for _ in range(8):
        strict.process(loud)
    assert not strict.is_open()
    loose = NoiseGate(threshold_db=-50.0)
    for _ in range(8):
        loose.process(loud)
    assert loose.is_open()


def test_noise_suppressor_processes_frame() -> None:
    suppressor = NoiseSuppressor(strength=0.8)
    frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
    out = suppressor.process(frame)
    assert out.shape == frame.shape


def test_noise_suppressor_strength_changes_output() -> None:
    np.random.seed(0)
    noisy = (np.random.randn(FRAME_SAMPLES) * 80).astype(np.int16)
    low = NoiseSuppressor(strength=0.1)
    high = NoiseSuppressor(strength=0.95)
    for _ in range(20):
        low_out = low.process(noisy)
        high_out = high.process(noisy)
    assert float(np.max(np.abs(high_out))) < float(np.max(np.abs(low_out)))


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
    assert len(codec.decode(b"\x01")) == FRAME_BYTES


def test_opus_codec_encode_rejects_empty() -> None:
    codec = OpusCodec()
    assert codec.encode(b"") is None


def test_opus_codec_oversized_packet_returns_silence() -> None:
    codec = OpusCodec()
    assert len(codec.decode(b"\xff" * 2000)) == FRAME_BYTES
