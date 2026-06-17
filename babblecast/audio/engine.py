"""Non-exclusive microphone capture via PortAudio shared streams."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from babblecast.audio.devices import resolve_input_device, resolve_output_device
from babblecast.audio.processing import NoiseGate, NoiseSuppressor, rms_db
from babblecast.constants import CHANNELS, FRAME_SAMPLES, SAMPLE_RATE

logger = logging.getLogger(__name__)


class MicCapture:
    """
    Opens a normal shared input stream — does not take exclusive control of
    the audio device (same model as Discord/Zoom alongside Spotify/YouTube).
    """

    def __init__(
        self,
        device_key: str | None,
        gate: NoiseGate,
        suppressor: NoiseSuppressor,
        on_frame: Callable[[bytes, float], None],
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        self._device_key = device_key
        self._gate = gate
        self._suppressor = suppressor
        self._on_frame = on_frame
        self._on_level = on_level
        self._stream: sd.InputStream | None = None
        self._buffer = np.zeros(0, dtype=np.int16)
        self._enabled = True
        self._ptt_active = False
        self._muted = False
        self._lock = threading.Lock()

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._muted = value

    @property
    def ptt_active(self) -> bool:
        return self._ptt_active

    @ptt_active.setter
    def ptt_active(self, value: bool) -> None:
        self._ptt_active = value

    def should_transmit(self) -> bool:
        if self._muted:
            return self._ptt_active
        return True

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("Input stream status: %s", status)
        if not self._enabled:
            return
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        samples = (mono * 32767.0).astype(np.int16) if mono.dtype == np.float32 else mono.astype(np.int16)
        self._buffer = np.concatenate([self._buffer, samples])
        while len(self._buffer) >= FRAME_SAMPLES:
            frame = self._buffer[:FRAME_SAMPLES]
            self._buffer = self._buffer[FRAME_SAMPLES:]
            if not self.should_transmit():
                if self._on_level:
                    self._on_level(0.0)
                continue
            processed = self._suppressor.process(frame)
            gated, level = self._gate.process(processed)
            if self._on_level:
                self._on_level(level if level > 0.05 else 0.0)
            if rms_db(gated) >= self._gate.threshold_db - 3:
                self._on_frame(gated.tobytes(), level)

    def start(self) -> None:
        if self._stream is not None:
            return
        device = resolve_input_device(self._device_key)
        self._stream = sd.InputStream(
            device=device,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES // 2,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        logger.info("Mic capture started on device index %s (shared/non-exclusive)", device)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def set_device(self, device_key: str | None) -> None:
        self._device_key = device_key
        was_running = self._stream is not None
        if was_running:
            self.stop()
            self.start()


class SpeakerOutput:
    """
    Mixed playback on a shared output stream — one more app in the mix,
    not replacing the system audio path.
    """

    def __init__(self, device_key: str | None, master_volume: float = 1.0) -> None:
        self._device_key = device_key
        self._master_volume = master_volume
        self._stream: sd.OutputStream | None = None
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)
        self._mix_lock = threading.Lock()
        self._participant_buffers: dict[str, queue.Queue[np.ndarray]] = {}
        self._participant_volumes: dict[str, float] = {}
        self._participant_muted: dict[str, bool] = {}
        self._worker: threading.Thread | None = None
        self._running = False

    def set_master_volume(self, value: float) -> None:
        self._master_volume = max(0.0, min(2.0, value))

    def set_participant_volume(self, client_id: str, volume: float) -> None:
        self._participant_volumes[client_id] = max(0.0, min(2.0, volume))

    def set_participant_muted(self, client_id: str, muted: bool) -> None:
        self._participant_muted[client_id] = muted

    def remove_participant(self, client_id: str) -> None:
        self._participant_buffers.pop(client_id, None)
        self._participant_volumes.pop(client_id, None)
        self._participant_muted.pop(client_id, None)

    def push_pcm(self, client_id: str, pcm: bytes) -> None:
        if self._participant_muted.get(client_id, False):
            return
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        buf = self._participant_buffers.setdefault(client_id, queue.Queue(maxsize=8))
        try:
            buf.put_nowait(arr)
        except queue.Full:
            try:
                buf.get_nowait()
            except queue.Empty:
                pass
            buf.put_nowait(arr)

    def _mix_frame(self) -> np.ndarray:
        mix = np.zeros(FRAME_SAMPLES, dtype=np.float32)
        for client_id, buf in list(self._participant_buffers.items()):
            if self._participant_muted.get(client_id, False):
                continue
            try:
                chunk = buf.get_nowait()
            except queue.Empty:
                continue
            vol = self._participant_volumes.get(client_id, 1.0)
            n = min(len(chunk), FRAME_SAMPLES)
            mix[:n] += chunk[:n] * vol
        mix = np.clip(mix * self._master_volume, -1.0, 1.0)
        return mix

    def _worker_loop(self) -> None:
        while self._running:
            frame = self._mix_frame()
            try:
                self._queue.put(frame, timeout=0.05)
            except queue.Full:
                pass

    def _callback(self, outdata, frames, time_info, status) -> None:
        try:
            frame = self._queue.get_nowait()
        except queue.Empty:
            frame = np.zeros(frames, dtype=np.float32)
        n = min(len(frame), frames)
        outdata[:n, 0] = frame[:n]
        if n < frames:
            outdata[n:, 0] = 0

    def start(self) -> None:
        if self._stream is not None:
            return
        device = resolve_output_device(self._device_key)
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="bbc-playback-mix")
        self._worker.start()
        self._stream = sd.OutputStream(
            device=device,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        logger.info("Speaker output started on device index %s (shared/non-exclusive)", device)

    def stop(self) -> None:
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def set_device(self, device_key: str | None) -> None:
        self._device_key = device_key
        was_running = self._stream is not None
        if was_running:
            self.stop()
            self.start()

