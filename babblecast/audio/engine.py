"""Non-exclusive microphone capture via PortAudio shared streams."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from babblecast.audio.input_routing import iter_mic_open_candidates
from babblecast.audio.portaudio import iter_output_device_indices
from babblecast.audio.processing import NoiseGate, NoiseSuppressor, apply_gain, level_db_to_meter, rms_db
from babblecast.audio.resample import native_frame_samples, resample_mono_to_48k
from babblecast.constants import (
    CHANNELS,
    FRAME_BYTES,
    FRAME_DURATION_SEC,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    VOICE_PLAYBACK_QUEUE_MAX,
)

logger = logging.getLogger(__name__)


def _close_stream_async(stream) -> None:
    """PortAudio stop/close can block; never call that on the Qt UI thread."""

    def _worker() -> None:
        try:
            stream.stop()
            stream.close()
        except Exception:
            logger.debug("Async PortAudio stream close failed", exc_info=True)

    threading.Thread(target=_worker, daemon=True, name="bbc-audio-close").start()


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
        self._input_volume = 1.0
        self._capture_rate = SAMPLE_RATE
        self._active_device_index: int | None = None
        self._active_device_name = ""
        self._active_route_kind = ""
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

    def set_input_volume(self, value: float) -> None:
        self._input_volume = max(0.0, min(2.0, value))

    @property
    def active_device_index(self) -> int | None:
        return self._active_device_index

    @property
    def active_device_name(self) -> str:
        return self._active_device_name

    @property
    def active_route_kind(self) -> str:
        return self._active_route_kind

    @property
    def capture_rate(self) -> int:
        return self._capture_rate

    def _process_frame(self, frame: np.ndarray) -> None:
        gained = apply_gain(frame, self._input_volume)
        processed = self._suppressor.process(gained)
        gated, level = self._gate.process(processed)
        if self._on_level:
            self._on_level(level_db_to_meter(rms_db(gated)))
        if not self.should_transmit():
            return
        if self._gate.is_open():
            self._on_frame(gated.tobytes(), level)

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("Input stream status: %s", status)
        if not self._enabled:
            return
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        samples = (mono * 32767.0).astype(np.int16) if mono.dtype == np.float32 else mono.astype(np.int16)
        self._buffer = np.concatenate([self._buffer, samples])
        if self._capture_rate == SAMPLE_RATE:
            while len(self._buffer) >= FRAME_SAMPLES:
                frame = self._buffer[:FRAME_SAMPLES]
                self._buffer = self._buffer[FRAME_SAMPLES:]
                self._process_frame(frame)
            return
        native_need = native_frame_samples(self._capture_rate)
        while len(self._buffer) >= native_need:
            chunk = self._buffer[:native_need]
            self._buffer = self._buffer[native_need:]
            frame = resample_mono_to_48k(chunk, self._capture_rate)
            self._process_frame(frame)

    def start(self) -> None:
        if self._stream is not None:
            return
        last_error: Exception | None = None
        for candidate in iter_mic_open_candidates(self._device_key):
            blocksize = max(FRAME_SAMPLES // 2, candidate.sample_rate // 100)
            try:
                self._capture_rate = candidate.sample_rate
                self._stream = sd.InputStream(
                    device=candidate.device_index,
                    channels=CHANNELS,
                    samplerate=candidate.sample_rate,
                    blocksize=blocksize,
                    dtype="float32",
                    callback=self._callback,
                )
                self._stream.start()
                self._enabled = True
                self._active_device_index = candidate.device_index
                self._active_route_kind = candidate.route_kind
                try:
                    self._active_device_name = str(
                        sd.query_devices(candidate.device_index)["name"]
                    )
                except Exception:
                    self._active_device_name = f"device {candidate.device_index}"
                logger.info(
                    "Mic capture started on device index %s @ %s Hz (%s, shared/non-exclusive)",
                    candidate.device_index,
                    candidate.sample_rate,
                    candidate.route_kind,
                )
                return
            except sd.PortAudioError as exc:
                last_error = exc
                logger.warning(
                    "Mic open failed on device %s @ %s Hz (%s): %s",
                    candidate.device_index,
                    candidate.sample_rate,
                    candidate.route_kind,
                    exc,
                )
                self._stream = None
        if last_error:
            raise last_error
        raise sd.PortAudioError("No input audio device available")

    def stop(self, *, teardown: bool = False) -> None:
        with self._lock:
            if teardown:
                self._enabled = False
                self._on_level = None
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._active_device_index = None
        self._active_device_name = ""
        self._active_route_kind = ""
        self._capture_rate = SAMPLE_RATE
        with self._lock:
            self._buffer = np.zeros(0, dtype=np.int16)

    def stop_fast(self) -> None:
        """Silence callbacks and close the stream on a background thread (app exit)."""
        with self._lock:
            self._enabled = False
            self._on_level = None
        stream = self._stream
        self._stream = None
        with self._lock:
            self._buffer = np.zeros(0, dtype=np.int16)
        if stream is not None:
            _close_stream_async(stream)

    def set_device(self, device_key: str | None) -> None:
        self._device_key = device_key
        if self._stream is not None:
            self.stop()
            time.sleep(0.05)
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
        self._active_device_index: int | None = None
        self._active_device_name: str = ""
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=VOICE_PLAYBACK_QUEUE_MAX)
        self._mix_lock = threading.Lock()
        self._participant_buffers: dict[str, queue.Queue[np.ndarray]] = {}
        self._participant_volumes: dict[str, float] = {}
        self._participant_muted: dict[str, bool] = {}
        self._worker: threading.Thread | None = None
        self._running = False

    def set_master_volume(self, value: float) -> None:
        self._master_volume = max(0.0, min(2.0, value))

    @property
    def active_device_index(self) -> int | None:
        return self._active_device_index

    @property
    def active_device_name(self) -> str:
        return self._active_device_name

    def set_participant_volume(self, client_id: str, volume: float) -> None:
        self._participant_volumes[client_id] = max(0.0, min(2.0, volume))

    def set_participant_muted(self, client_id: str, muted: bool) -> None:
        self._participant_muted[client_id] = muted

    def remove_participant(self, client_id: str) -> None:
        self._participant_buffers.pop(client_id, None)
        self._participant_volumes.pop(client_id, None)
        self._participant_muted.pop(client_id, None)

    def push_pcm(self, client_id: str, pcm: bytes) -> None:
        if self._stream is None or len(pcm) != FRAME_BYTES:
            return
        if self._participant_muted.get(client_id, False):
            return
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        buf = self._participant_buffers.setdefault(client_id, queue.Queue(maxsize=VOICE_PLAYBACK_QUEUE_MAX))
        try:
            buf.put_nowait(arr)
        except queue.Full:
            logger.debug("Participant %s playback queue full; dropping oldest frame", client_id)
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
        next_tick = time.monotonic()
        while self._running:
            frame = self._mix_frame()
            try:
                self._queue.put(frame, timeout=0.02)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(frame)
                except queue.Full:
                    logger.debug("Output mix queue full; dropping newest frame")
            next_tick += FRAME_DURATION_SEC
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            elif sleep_for < -FRAME_DURATION_SEC:
                next_tick = time.monotonic()

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
        last_error: Exception | None = None
        for device in iter_output_device_indices(self._device_key):
            self._running = True
            self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="bbc-playback-mix")
            self._worker.start()
            try:
                self._stream = sd.OutputStream(
                    device=device,
                    channels=CHANNELS,
                    samplerate=SAMPLE_RATE,
                    blocksize=FRAME_SAMPLES,
                    dtype="float32",
                    callback=self._callback,
                )
                self._stream.start()
                self._active_device_index = device
                try:
                    self._active_device_name = str(sd.query_devices(device)["name"])
                except Exception:
                    self._active_device_name = f"device {device}"
                logger.info("Speaker output started on device index %s (shared/non-exclusive)", device)
                return
            except sd.PortAudioError as exc:
                last_error = exc
                logger.warning("Speaker open failed on device %s: %s", device, exc)
                self._running = False
                if self._worker:
                    self._worker.join(timeout=0.5)
                self._worker = None
                self._stream = None
        if last_error:
            raise last_error
        raise sd.PortAudioError("No output audio device available")

    def stop(self) -> None:
        self._running = False
        worker = self._worker
        if worker:
            worker.join(timeout=1.0)
            self._worker = None
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._active_device_index = None
        self._active_device_name = ""

    def stop_fast(self) -> None:
        """Stop mixing callbacks and close the stream on a background thread (app exit)."""
        self._running = False
        self._worker = None
        stream = self._stream
        self._stream = None
        if stream is not None:
            _close_stream_async(stream)

    def set_device(self, device_key: str | None) -> None:
        self._device_key = device_key
        was_running = self._stream is not None
        if was_running:
            self.stop()
            time.sleep(0.05)
            self.start()

