"""PCM resampling helpers for non-48 kHz capture devices."""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import resample_poly

from babblecast.constants import FRAME_SAMPLES, SAMPLE_RATE


def native_frame_samples(capture_rate: int) -> int:
    """Input samples needed per 20 ms frame at *capture_rate* (before resampling to 48 kHz)."""
    if capture_rate == SAMPLE_RATE:
        return FRAME_SAMPLES
    return max(1, int(round(FRAME_SAMPLES * capture_rate / SAMPLE_RATE)))


def resample_mono_to_48k(samples: np.ndarray, capture_rate: int) -> np.ndarray:
    """Resample mono int16/float32 PCM to FRAME_SAMPLES @ 48 kHz."""
    if capture_rate == SAMPLE_RATE:
        out = samples.astype(np.int16, copy=False)
        if len(out) < FRAME_SAMPLES:
            out = np.pad(out, (0, FRAME_SAMPLES - len(out)))
        return out[:FRAME_SAMPLES]
    if len(samples) == 0:
        return np.zeros(FRAME_SAMPLES, dtype=np.int16)
    if samples.dtype == np.int16:
        work = samples.astype(np.float32) / 32768.0
    else:
        work = samples.astype(np.float32, copy=False)
    gcd = math.gcd(capture_rate, SAMPLE_RATE)
    up = SAMPLE_RATE // gcd
    down = capture_rate // gcd
    resampled = resample_poly(work, up, down)
    if len(resampled) < FRAME_SAMPLES:
        resampled = np.pad(resampled, (0, FRAME_SAMPLES - len(resampled)))
    clipped = np.clip(resampled[:FRAME_SAMPLES], -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)
