"""Android audio via AudioRecord / AudioTrack (shared-mode, non-exclusive)."""

from __future__ import annotations

import logging
import queue
import threading
import time

import numpy as np

from babblecast.audio.android_routing import get_android_router, normalize_audio_route
from babblecast.audio.processing import NoiseGate, NoiseSuppressor, apply_gain, level_db_to_meter, rms_db
from babblecast.constants import (
    CHANNELS,
    FRAME_BYTES,
    FRAME_DURATION_SEC,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    VOICE_PLAYBACK_QUEUE_MAX,
)

logger = logging.getLogger(__name__)


def _jni():
    from jnius import autoclass

    return autoclass


class AndroidMicCapture:
    def __init__(
        self,
        device_key: str | None,
        gate: NoiseGate,
        suppressor: NoiseSuppressor,
        on_frame,
        on_level=None,
    ) -> None:
        self._gate = gate
        self._suppressor = suppressor
        self._on_frame = on_frame
        self._on_level = on_level
        self._muted = False
        self._ptt_active = False
        self._input_volume = 1.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._record = None

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

    def _loop(self) -> None:
        buf_size = FRAME_SAMPLES * 4
        data = bytearray(buf_size)
        while self._running:
            n = self._record.read(data, 0, buf_size)
            if n <= 0:
                continue
            samples = np.frombuffer(bytes(data[:n]), dtype=np.int16)
            if len(samples) < FRAME_SAMPLES:
                continue
            for i in range(0, len(samples) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
                frame = samples[i : i + FRAME_SAMPLES]
                gained = apply_gain(frame, self._input_volume)
                processed = self._suppressor.process(gained.copy())
                gated, level = self._gate.process(processed)
                if self._on_level:
                    self._on_level(level_db_to_meter(rms_db(gated)))
                if not self.should_transmit():
                    continue
                if self._gate.is_open():
                    self._on_frame(gated.tobytes(), level)

    def start(self) -> None:
        if self._thread:
            return
        autoclass = _jni()
        AudioFormat = autoclass("android.media.AudioFormat")
        AudioRecord = autoclass("android.media.AudioRecord")
        AudioSource = autoclass("android.media.MediaRecorder$AudioSource")
        min_buf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if min_buf <= 0:
            raise RuntimeError(f"AudioRecord.getMinBufferSize failed: {min_buf}")
        self._record = AudioRecord(
            AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            min_buf * 2,
        )
        if self._record.getState() != 1:  # STATE_INITIALIZED
            raise RuntimeError("AudioRecord failed to initialize")
        self._record.startRecording()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bbc-android-mic")
        self._thread.start()
        logger.info("Android mic capture started")

    def stop(self, *, teardown: bool = False) -> None:
        self._running = False
        if teardown:
            self._on_level = None
        if self._record:
            try:
                self._record.stopRecording()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self._record:
            try:
                self._record.stop()
                self._record.release()
            except Exception:
                pass
            self._record = None

    def set_device(self, device_key: str | None) -> None:
        pass

    @property
    def running(self) -> bool:
        return self._running

    def restart(self) -> None:
        if not self._running:
            return
        on_level = self._on_level
        self.stop()
        self._on_level = on_level
        self.start()


class AndroidSpeakerOutput:
    def __init__(self, device_key: str | None, master_volume: float = 1.0) -> None:
        self._master_volume = master_volume
        self._participant_buffers: dict[str, queue.Queue[np.ndarray]] = {}
        self._participant_volumes: dict[str, float] = {}
        self._participant_muted: dict[str, bool] = {}
        self._track = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._route = normalize_audio_route(None)

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
        if len(pcm) != FRAME_BYTES:
            return
        if self._participant_muted.get(client_id, False):
            return
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        buf = self._participant_buffers.setdefault(client_id, queue.Queue(maxsize=VOICE_PLAYBACK_QUEUE_MAX))
        try:
            buf.put_nowait(arr)
        except queue.Full:
            try:
                buf.get_nowait()
            except queue.Empty:
                pass
            buf.put_nowait(arr)

    def _mix(self) -> np.ndarray:
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
        return np.clip(mix * self._master_volume, -1.0, 1.0)

    def _loop(self) -> None:
        pcm = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        next_tick = time.monotonic()
        while self._running:
            frame = self._mix()
            pcm = (frame * 32767.0).astype(np.int16)
            self._track.write(pcm.tobytes(), 0, len(pcm) * 2)
            next_tick += FRAME_DURATION_SEC
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            elif sleep_for < -FRAME_DURATION_SEC:
                next_tick = time.monotonic()

    def _create_track(self, autoclass, AudioFormat, AudioTrack, min_buf: int):
        """Prefer AudioAttributes (VoIP) over legacy STREAM_VOICE_CALL → earpiece."""
        try:
            attrs_builder = autoclass("android.media.AudioAttributes").Builder()
            attrs_builder.setUsage(autoclass("android.media.AudioAttributes").USAGE_VOICE_COMMUNICATION)
            attrs_builder.setContentType(autoclass("android.media.AudioAttributes").CONTENT_TYPE_SPEECH)
            attrs = attrs_builder.build()
            fmt_builder = AudioFormat.Builder()
            fmt_builder.setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            fmt_builder.setSampleRate(SAMPLE_RATE)
            fmt_builder.setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
            fmt = fmt_builder.build()
            return AudioTrack(
                attrs,
                fmt,
                min_buf * 2,
                AudioTrack.MODE_STREAM,
                0,
            )
        except Exception:
            logger.debug("AudioAttributes AudioTrack failed; falling back to legacy stream type", exc_info=True)
            AudioManager = autoclass("android.media.AudioManager")
            return AudioTrack(
                AudioManager.STREAM_MUSIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                min_buf * 2,
                AudioTrack.MODE_STREAM,
            )

    def start(self, *, route: str | None = None) -> None:
        if self._thread:
            return
        self._route = normalize_audio_route(route or get_android_router().route)
        get_android_router().apply(self._route)
        autoclass = _jni()
        AudioFormat = autoclass("android.media.AudioFormat")
        AudioTrack = autoclass("android.media.AudioTrack")
        min_buf = AudioTrack.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if min_buf <= 0:
            raise RuntimeError(f"AudioTrack.getMinBufferSize failed: {min_buf}")
        self._track = self._create_track(autoclass, AudioFormat, AudioTrack, min_buf)
        self._track.play()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bbc-android-spk")
        self._thread.start()
        logger.info("Android speaker output started (route=%s)", self._route)

    def stop(self) -> None:
        self._running = False
        if self._track:
            try:
                self._track.pause()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self._track:
            try:
                self._track.stop()
                self._track.release()
            except Exception:
                pass
            self._track = None
        get_android_router().shutdown()

    def set_device(self, device_key: str | None) -> None:
        if device_key:
            self.set_route(device_key)

    def set_route(self, route: str, *, mic_restart_cb=None) -> None:
        route = normalize_audio_route(route)
        if route == self._route and self._thread:
            return
        self._route = route
        get_android_router().apply(route, mic_restart_cb=mic_restart_cb)
        logger.info("Android speaker route hot-swapped → %s", route)
