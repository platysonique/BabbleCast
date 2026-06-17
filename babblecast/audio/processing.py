"""Voice processing: noise gate and spectral noise suppression."""

from __future__ import annotations

import logging
import math

import numpy as np

from babblecast.constants import FRAME_SAMPLES, SAMPLE_RATE

logger = logging.getLogger(__name__)

_FRAME_MS = 1000.0 * FRAME_SAMPLES / SAMPLE_RATE


def rms_db(samples: np.ndarray) -> float:
    """RMS level in dBFS (0 dB = full-scale int16)."""
    if samples.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    if rms < 1.0:
        return -120.0
    return 20.0 * np.log10(rms / 32768.0)


def apply_gain(samples: np.ndarray, gain: float) -> np.ndarray:
    """Scale int16 PCM by gain (0–2.0) with clipping."""
    if gain == 1.0:
        return samples
    scaled = samples.astype(np.float32) * gain
    return np.clip(scaled, -32768.0, 32767.0).astype(np.int16)


def level_db_to_meter(level_db: float, *, floor_db: float = -60.0) -> float:
    """Map dBFS to 0..1 for VU display (-60 dB = silence, 0 dB = full scale)."""
    return max(0.0, min(1.0, (level_db - floor_db) / -floor_db))


class NoiseGate:
    """Software noise gate — envelope opens/closes over ~5 ms attack, ~120 ms release."""

    def __init__(
        self,
        threshold_db: float = -40.0,
        *,
        attack_ms: float = 5.0,
        release_ms: float = 120.0,
    ) -> None:
        self.threshold_db = threshold_db
        self._attack_ms = attack_ms
        self._release_ms = release_ms
        self._envelope = 0.0

    def set_threshold_db(self, value: float) -> None:
        self.threshold_db = max(-80.0, min(0.0, value))

    def is_open(self) -> bool:
        return self._envelope > 0.08

    def _step_coef(self, ms: float) -> float:
        return 1.0 - math.exp(-_FRAME_MS / max(ms, 1.0))

    def process(self, samples: np.ndarray) -> tuple[np.ndarray, float]:
        level_db = rms_db(samples)
        target = 1.0 if level_db >= self.threshold_db else 0.0
        coef = self._step_coef(self._attack_ms) if target > self._envelope else self._step_coef(self._release_ms)
        self._envelope += coef * (target - self._envelope)
        gated = (samples.astype(np.float32) * self._envelope).astype(np.int16)
        return gated, level_db_to_meter(rms_db(gated))


class NoiseSuppressor:
    """Noise reduction — noisereduce when available, RMS expander fallback otherwise."""

    def __init__(self, strength: float = 0.5) -> None:
        self.strength = strength
        self._nr = None
        self._nr_missing_logged = False
        self._profile: np.ndarray | None = None
        self._profile_frames = 0
        self._noise_floor_db = -55.0

    def _ensure_nr(self) -> bool:
        if self._nr is None:
            try:
                import noisereduce as nr
            except ImportError:
                if not self._nr_missing_logged:
                    logger.info("noisereduce not installed — using built-in noise expander")
                    self._nr_missing_logged = True
                return False
            self._nr = nr
        return True

    def set_strength(self, value: float) -> None:
        self.strength = max(0.0, min(1.0, value))
        self._profile = None
        self._profile_frames = 0

    def _fallback(self, samples: np.ndarray) -> np.ndarray:
        """Lightweight expander — works on every 20 ms frame without scipy/noisereduce."""
        level_db = rms_db(samples)
        if level_db < self._noise_floor_db:
            self._noise_floor_db = 0.92 * self._noise_floor_db + 0.08 * level_db
        margin_db = 6.0 + self.strength * 18.0
        if level_db >= self._noise_floor_db + margin_db:
            return samples
        if level_db <= self._noise_floor_db:
            gain = 1.0 - self.strength
        else:
            t = (level_db - self._noise_floor_db) / max(margin_db, 0.1)
            gain = 1.0 - self.strength * (1.0 - t)
        return (samples.astype(np.float32) * gain).astype(np.int16)

    def process(self, samples: np.ndarray) -> np.ndarray:
        if self.strength <= 0.01:
            return samples
        if not self._ensure_nr():
            return self._fallback(samples)
        assert self._nr is not None
        float_samples = samples.astype(np.float32) / 32768.0
        if self._profile is None and self._profile_frames < 8:
            if self._profile is None:
                self._profile = float_samples.copy()
            else:
                self._profile = np.concatenate([self._profile, float_samples])
            self._profile_frames += 1
            if len(self._profile) < FRAME_SAMPLES:
                return self._fallback(samples)
        prop = 0.15 + self.strength * 0.85
        try:
            reduced = self._nr.reduce_noise(
                y=float_samples,
                sr=SAMPLE_RATE,
                y_noise=self._profile,
                prop_decrease=prop,
                stationary=True,
            )
        except Exception as exc:
            logger.debug("noisereduce failed: %s", exc)
            return self._fallback(samples)
        if len(reduced) != len(float_samples):
            return self._fallback(samples)
        return (np.clip(reduced, -1.0, 1.0) * 32767.0).astype(np.int16)
