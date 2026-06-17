"""Voice processing: noise gate and spectral noise suppression."""

from __future__ import annotations

import numpy as np

from babblecast.constants import SAMPLE_RATE


def rms_db(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    if rms < 1e-10:
        return -120.0
    return 20.0 * np.log10(rms)


class NoiseGate:
    """Software noise gate — does not touch system audio routing."""

    def __init__(self, threshold_db: float = -40.0, attack: float = 0.01, release: float = 0.08) -> None:
        self.threshold_db = threshold_db
        self.attack = attack
        self.release = release
        self._envelope = 0.0

    def set_threshold_db(self, value: float) -> None:
        self.threshold_db = max(-80.0, min(0.0, value))

    def process(self, samples: np.ndarray) -> tuple[np.ndarray, float]:
        level_db = rms_db(samples)
        target = 1.0 if level_db >= self.threshold_db else 0.0
        coeff = self.attack if target > self._envelope else self.release
        self._envelope += coeff * (target - self._envelope)
        gated = (samples.astype(np.float32) * self._envelope).astype(np.int16)
        normalized = max(0.0, min(1.0, (level_db + 60.0) / 60.0))
        return gated, normalized


class NoiseSuppressor:
    """Spectral noise reduction via noisereduce — in-process only."""

    def __init__(self, strength: float = 0.5) -> None:
        self.strength = strength
        self._nr = None
        self._profile: np.ndarray | None = None
        self._profile_frames = 0

    def _ensure(self) -> None:
        if self._nr is None:
            import noisereduce as nr

            self._nr = nr

    def set_strength(self, value: float) -> None:
        self.strength = max(0.0, min(1.0, value))

    def process(self, samples: np.ndarray) -> np.ndarray:
        if self.strength <= 0.01:
            return samples
        self._ensure()
        assert self._nr is not None
        float_samples = samples.astype(np.float32) / 32768.0
        if self._profile is None and self._profile_frames < 5:
            self._profile = float_samples.copy()
            self._profile_frames += 1
            return samples
        prop = 0.2 + self.strength * 0.75
        reduced = self._nr.reduce_noise(
            y=float_samples,
            sr=SAMPLE_RATE,
            y_noise=self._profile,
            prop_decrease=prop,
            stationary=True,
        )
        return (np.clip(reduced, -1.0, 1.0) * 32767.0).astype(np.int16)
