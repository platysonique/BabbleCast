"""Noise gate and device label tests."""

from __future__ import annotations

import numpy as np

from babblecast.audio.processing import NoiseGate, rms_db


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
