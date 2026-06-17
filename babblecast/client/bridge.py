"""Multi-server bridge — one mic/speaker, many simultaneous server links."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from babblecast.audio.factory import create_mic, create_speaker
from babblecast.audio.processing import NoiseGate, NoiseSuppressor
from babblecast.client.session import ClientSession
from babblecast.config import UserSettings, get_settings, save_settings
from babblecast.protocol import new_id

logger = logging.getLogger(__name__)


@dataclass
class ServerLinkState:
    link_id: str
    label: str
    host: str
    port: int
    listen_muted: bool = False
    mic_muted: bool = False
    connected: bool = False
    client_id: str = ""
    server_name: str = ""
    pending_taps: set[str] = field(default_factory=set)


class BridgeManager:
    """
    Connect to multiple BabbleCast servers at once with shared audio I/O.
    Per-link listen mute silences incoming audio from that server.
    Per-link mic mute stops sending your voice to that server only.
    """

    def __init__(
        self,
        on_link_connected: Callable[[str], None] | None = None,
        on_link_disconnected: Callable[[str, str], None] | None = None,
        on_presence: Callable[[str, str, list[dict]], None] | None = None,
        on_chat: Callable[[str, dict], None] | None = None,
        on_rooms: Callable[[str, list[dict]], None] | None = None,
        on_joined: Callable[[str, str, str], None] | None = None,
        on_room_deleted: Callable[[str, str], None] | None = None,
        on_error: Callable[[str, str, str | None], None] | None = None,
        on_tap_received: Callable[[str, dict], None] | None = None,
        on_tap_chat: Callable[[str, dict], None] | None = None,
        on_tap_open: Callable[[str, str], None] | None = None,
        on_tap_end: Callable[[str, str], None] | None = None,
    ) -> None:
        self._settings = get_settings()
        self._on_link_connected = on_link_connected
        self._on_link_disconnected = on_link_disconnected
        self._on_presence = on_presence
        self._on_chat = on_chat
        self._on_rooms = on_rooms
        self._on_joined = on_joined
        self._on_room_deleted = on_room_deleted
        self._on_error = on_error
        self._on_tap_received = on_tap_received
        self._on_tap_chat = on_tap_chat
        self._on_tap_open = on_tap_open
        self._on_tap_end = on_tap_end
        self._links: dict[str, ServerLinkState] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._lock = threading.Lock()
        self._gate = NoiseGate(threshold_db=self._settings.gate_threshold_db)
        self._suppressor = NoiseSuppressor(strength=self._settings.noise_suppression)
        self._mic = None
        self._speaker = None
        self._audio_started = False
        self._global_muted = False
        self._global_ptt = False

    @property
    def links(self) -> list[ServerLinkState]:
        with self._lock:
            return list(self._links.values())

    def get_link(self, link_id: str) -> ServerLinkState | None:
        return self._links.get(link_id)

    def get_session(self, link_id: str) -> ClientSession | None:
        return self._sessions.get(link_id)

    def _ensure_audio(self) -> bool:
        """Start shared mic/speaker. Returns False if hardware could not open."""
        if self._audio_started:
            return True
        self._mic = create_mic(
            device_key=self._settings.input_device,
            gate=self._gate,
            suppressor=self._suppressor,
            on_frame=self._on_mic_frame,
            on_level=self._on_mic_level,
        )
        self._speaker = create_speaker(
            device_key=self._settings.output_device,
            master_volume=self._settings.output_volume,
        )
        for uid, vol in self._settings.per_user_volumes.items():
            self._speaker.set_participant_volume(uid, vol)
        for uid, muted in self._settings.per_user_muted.items():
            self._speaker.set_participant_muted(uid, muted)
        try:
            self._speaker.start()
            self._mic.start()
        except Exception as exc:
            logger.exception("Bridge audio startup failed")
            self._teardown_audio()
            return False
        self._audio_started = True
        return True

    def _teardown_audio(self) -> None:
        if self._mic:
            self._mic.stop()
            self._mic = None
        if self._speaker:
            self._speaker.stop()
            self._speaker = None
        self._audio_started = False

    def _stop_audio_if_idle(self) -> None:
        if self._sessions:
            return
        self._teardown_audio()

    def _on_mic_frame(self, pcm: bytes, _level: float) -> None:
        for link_id, session in list(self._sessions.items()):
            link = self._links.get(link_id)
            if (
                link
                and not link.mic_muted
                and session.connected
                and session.room_id
            ):
                session.send_voice_pcm(bytes(pcm))

    def _on_mic_level(self, level: float) -> None:
        for link_id, session in list(self._sessions.items()):
            link = self._links.get(link_id)
            if link and not link.mic_muted and session.connected:
                session.send_voice_level(level)

    def connect(self, host: str, port: int = 8765, label: str | None = None) -> str:
        link_id = new_id()
        display = label or f"{host}:{port}"
        state = ServerLinkState(link_id=link_id, label=display, host=host, port=port)
        with self._lock:
            self._links[link_id] = state

        def _connected() -> None:
            state.connected = True
            session = self._sessions.get(link_id)
            if session:
                state.client_id = session.client_id
                if session.server_name:
                    state.server_name = session.server_name
                    state.label = f"{session.server_name} ({state.host})"
            if self._on_link_connected:
                self._on_link_connected(link_id)

        session = ClientSession(
            link_id=link_id,
            bridge_speaker=self._speaker,
            on_presence=lambda rid, p, lid=link_id: self._on_presence and self._on_presence(lid, rid, p),
            on_chat=lambda d, lid=link_id: self._on_chat and self._on_chat(lid, d),
            on_rooms=lambda r, lid=link_id: self._on_rooms and self._on_rooms(lid, r),
            on_joined=lambda rid, rn, lid=link_id: self._on_joined and self._on_joined(lid, rid, rn),
            on_room_deleted=lambda rid, lid=link_id: self._on_room_deleted and self._on_room_deleted(lid, rid),
            on_connected=_connected,
            on_disconnected=lambda reason, lid=link_id: self._handle_disconnect(lid, reason),
            on_error=lambda m, ec, lid=link_id: self._on_error and self._on_error(lid, m, ec),
            on_tap_received=lambda d, lid=link_id: self._handle_tap_received(lid, d),
            on_tap_chat=lambda d, lid=link_id: self._on_tap_chat and self._on_tap_chat(lid, d),
            on_tap_open=lambda tid, lid=link_id: self._handle_tap_open(lid, tid),
            on_tap_end=lambda tid, lid=link_id: self._handle_tap_end(lid, tid),
            listen_muted_getter=lambda lid=link_id: self._links[lid].listen_muted,
        )
        self._sessions[link_id] = session
        if not self._ensure_audio():
            if self._on_error:
                self._on_error(
                    link_id,
                    "Audio unavailable — connected for chat only; check speakers/mic",
                    None,
                )
        session.update_settings(self._settings)
        session.connect(host, port)
        return link_id

    def _handle_disconnect(self, link_id: str, reason: str) -> None:
        link = self._links.get(link_id)
        was_connected = bool(link and link.connected)
        if link:
            link.connected = False
        if not was_connected:
            self._sessions.pop(link_id, None)
            with self._lock:
                self._links.pop(link_id, None)
            self._stop_audio_if_idle()
        if self._on_link_disconnected:
            self._on_link_disconnected(link_id, reason)

    def _handle_tap_received(self, link_id: str, data: dict[str, Any]) -> None:
        link = self._links.get(link_id)
        if link and not data.get("self_sent"):
            from_id = str(data.get("from_id", ""))
            link.pending_taps.add(from_id)
        if self._on_tap_received:
            self._on_tap_received(link_id, data)

    def _handle_tap_open(self, link_id: str, tap_id: str) -> None:
        if self._on_tap_open:
            self._on_tap_open(link_id, tap_id)

    def _handle_tap_end(self, link_id: str, tap_id: str) -> None:
        if self._on_tap_end:
            self._on_tap_end(link_id, tap_id)

    def disconnect(self, link_id: str) -> None:
        session = self._sessions.pop(link_id, None)
        if session:
            session.disconnect()
        with self._lock:
            self._links.pop(link_id, None)
        self._stop_audio_if_idle()

    def disconnect_all(self) -> None:
        for link_id in list(self._sessions.keys()):
            self.disconnect(link_id)

    def set_listen_muted(self, link_id: str, muted: bool) -> None:
        link = self._links.get(link_id)
        if link:
            link.listen_muted = muted

    def set_mic_muted(self, link_id: str, muted: bool) -> None:
        link = self._links.get(link_id)
        if link:
            link.mic_muted = muted
        session = self._sessions.get(link_id)
        if session:
            session.set_bridge_mic_muted(muted)

    def set_global_muted(self, muted: bool) -> None:
        self._global_muted = muted
        if self._mic:
            self._mic.muted = muted
        for session in self._sessions.values():
            session.set_muted(muted)

    def set_global_ptt(self, active: bool) -> None:
        self._global_ptt = active
        if self._mic:
            self._mic.ptt_active = active
        for session in self._sessions.values():
            session.set_ptt(active)

    def set_gate_db(self, value: float) -> None:
        self._gate.set_threshold_db(value)
        self._settings.gate_threshold_db = value
        save_settings(self._settings)

    def set_noise_suppression(self, value: float) -> None:
        self._suppressor.set_strength(value)
        self._settings.noise_suppression = value
        save_settings(self._settings)

    def set_input_device(self, device_key: str | None) -> None:
        self._settings.input_device = device_key
        save_settings(self._settings)
        if self._mic:
            self._mic.set_device(device_key)

    def set_output_device(self, device_key: str | None) -> None:
        self._settings.output_device = device_key
        save_settings(self._settings)
        if self._speaker:
            self._speaker.set_device(device_key)

    def set_participant_volume(self, composite_key: str, volume: float) -> None:
        self._settings.per_user_volumes[composite_key] = volume
        save_settings(self._settings)
        if self._speaker:
            self._speaker.set_participant_volume(composite_key, volume)
        link_id, _, client_id = composite_key.partition(":")
        if link_id and client_id:
            session = self._sessions.get(link_id)
            if session:
                session.set_participant_volume(client_id, volume)

    def set_participant_muted(self, composite_key: str, muted: bool) -> None:
        self._settings.per_user_muted[composite_key] = muted
        save_settings(self._settings)
        if self._speaker:
            self._speaker.set_participant_muted(composite_key, muted)
        link_id, _, client_id = composite_key.partition(":")
        if link_id and client_id:
            session = self._sessions.get(link_id)
            if session:
                session.set_participant_muted(client_id, muted)

    def send_chat(self, link_id: str, text: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.send_chat(text)

    def send_tap(self, link_id: str, target_id: str, text: str = "") -> None:
        session = self._sessions.get(link_id)
        if session:
            session.send_tap(target_id, text)

    def open_tap(self, link_id: str, tap_id: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.open_tap(tap_id)

    def send_tap_chat(self, link_id: str, tap_id: str, text: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.send_tap_chat(tap_id, text)

    def end_tap(self, link_id: str, tap_id: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.end_tap(tap_id)

    def clear_pending_tap(self, link_id: str, peer_id: str) -> None:
        link = self._links.get(link_id)
        if link:
            link.pending_taps.discard(peer_id)

    def update_settings(self, settings: UserSettings) -> None:
        self._settings = settings
        for session in self._sessions.values():
            session.update_settings(settings)

    def create_room(self, link_id: str, name: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.create_room(name)

    def delete_room(self, link_id: str, room_id: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.delete_room(room_id)

    def join_room(self, link_id: str, room_id: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.join_room(room_id)

    def request_rooms(self, link_id: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.request_rooms()

    @property
    def speaker(self):
        return self._speaker
