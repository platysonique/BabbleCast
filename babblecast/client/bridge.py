"""Multi-server bridge — one mic/speaker, many simultaneous server links."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from babblecast.active_tap_chats import get_active_tap_chat_store
from babblecast.audio.factory import create_mic, create_speaker, platform_name
from babblecast.audio.processing import NoiseGate, NoiseSuppressor
from babblecast.client.session import ClientSession
from babblecast.config import UserSettings, get_settings, save_settings
from babblecast.constants import DEFAULT_WS_PORT, VOICE_LEVEL_WS_MIN_INTERVAL_SEC
from babblecast.protocol import new_id
from babblecast.room_secrets import (
    forget_room_password,
    get_room_password,
    remember_room_password,
    room_password_admin_display,
)

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
    is_server_operator: bool = False
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
        on_local_mic_level: Callable[[float], None] | None = None,
        on_audio_route_changed: Callable[[str], None] | None = None,
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
        self._on_local_mic_level = on_local_mic_level
        self._on_audio_route_changed = on_audio_route_changed
        self._local_mic_level = 0.0
        self._last_ws_level_sent = 0.0
        self._pending_create_password: dict[str, tuple[str, str]] = {}
        self._pending_join_password: dict[str, tuple[str, str]] = {}
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
        self._monitoring_requested = False
        self._shutting_down = False

    @property
    def shutting_down(self) -> bool:
        return self._shutting_down

    def shutdown(self) -> None:
        """Stop audio and clear UI callbacks — safe to call from closeEvent."""
        self._shutting_down = True
        self._monitoring_requested = False
        self._on_link_connected = None
        self._on_link_disconnected = None
        self._on_presence = None
        self._on_chat = None
        self._on_rooms = None
        self._on_joined = None
        self._on_room_deleted = None
        self._on_error = None
        self._on_tap_received = None
        self._on_tap_chat = None
        self._on_tap_open = None
        self._on_tap_end = None
        self._on_local_mic_level = None
        self._on_audio_route_changed = None
        for link_id in list(self._sessions.keys()):
            session = self._sessions.pop(link_id, None)
            if session:
                session.disconnect(notify=False)
        with self._lock:
            self._links.clear()
        self._teardown_audio()

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
        if self._shutting_down or self._audio_started:
            return self._audio_started
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
            if platform_name() == "android":
                from babblecast.audio.android_routing import (
                    AUDIO_ROUTE_BLUETOOTH,
                    get_android_router,
                    normalize_audio_route,
                )

                initial_route = normalize_audio_route(self._settings.android_audio_route)
                if get_android_router().bluetooth_available():
                    initial_route = AUDIO_ROUTE_BLUETOOTH
                self._speaker.start(route=initial_route)
                if initial_route == AUDIO_ROUTE_BLUETOOTH:
                    self._settings.android_audio_route = AUDIO_ROUTE_BLUETOOTH
                    save_settings(self._settings)
            else:
                self._speaker.start()
            self._mic.set_input_volume(self._settings.input_volume)
            self._mic.start()
        except Exception as exc:
            logger.exception("Bridge audio startup failed")
            self._teardown_audio()
            return False
        self._audio_started = True
        if platform_name() == "android":
            self._start_android_bt_watch()
        return True

    def _start_android_bt_watch(self) -> None:
        from babblecast.audio.android_bt_watch import start_bluetooth_watch
        from babblecast.audio.android_routing import AUDIO_ROUTE_BLUETOOTH, AUDIO_ROUTE_SPEAKER

        start_bluetooth_watch(
            on_connected=lambda: self.set_audio_route(AUDIO_ROUTE_BLUETOOTH),
            on_disconnected=lambda: self.set_audio_route(AUDIO_ROUTE_SPEAKER),
        )

    def _notify_audio_route_changed(self, route: str) -> None:
        if self._on_audio_route_changed:
            try:
                self._on_audio_route_changed(route)
            except RuntimeError:
                pass

    def _teardown_audio(self) -> None:
        if platform_name() == "android":
            from babblecast.audio.android_bt_watch import stop_bluetooth_watch

            stop_bluetooth_watch()
        if self._mic:
            try:
                self._mic.stop(teardown=True)
            except Exception:
                logger.exception("Mic teardown failed")
            self._mic = None
        if self._speaker:
            try:
                self._speaker.stop()
            except Exception:
                logger.exception("Speaker teardown failed")
            self._speaker = None
        self._audio_started = False

    def disconnect_all(self) -> None:
        if self._shutting_down:
            return
        for link_id in list(self._sessions.keys()):
            self.disconnect(link_id)
        self._stop_audio_if_idle()

    def _stop_audio_if_idle(self) -> None:
        if self._sessions or self._monitoring_requested:
            return
        self._teardown_audio()

    def ensure_input_monitoring(self) -> bool:
        """Open shared mic/speaker so local meters work (even when not in a room)."""
        self._monitoring_requested = True
        return self._ensure_audio()

    def release_input_monitoring(self) -> None:
        self._monitoring_requested = False
        if not self._sessions:
            self._teardown_audio()

    def _on_mic_frame(self, pcm: bytes, _level: float) -> None:
        if self._shutting_down:
            return
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
        if self._shutting_down:
            return
        self._local_mic_level = level
        if self._on_local_mic_level:
            try:
                self._on_local_mic_level(level)
            except RuntimeError:
                pass
        now = time.monotonic()
        if now - self._last_ws_level_sent < VOICE_LEVEL_WS_MIN_INTERVAL_SEC:
            return
        self._last_ws_level_sent = now
        for link_id, session in list(self._sessions.items()):
            link = self._links.get(link_id)
            if link and not link.mic_muted and session.connected:
                session.send_voice_level(level)

    def connect(
        self,
        host: str,
        port: int = DEFAULT_WS_PORT,
        label: str | None = None,
        password: str = "",
        *,
        server_operator: bool = False,
    ) -> str:
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
                state.is_server_operator = session.is_server_operator
                if session.server_name:
                    state.server_name = session.server_name
                    state.label = session.server_name
            if self._on_link_connected:
                self._on_link_connected(link_id)

        session = ClientSession(
            link_id=link_id,
            bridge_speaker=self._speaker,
            on_presence=lambda rid, p, lid=link_id: self._on_presence and self._on_presence(lid, rid, p),
            on_chat=lambda d, lid=link_id: self._on_chat and self._on_chat(lid, d),
            on_rooms=lambda r, lid=link_id: self._on_rooms and self._on_rooms(lid, r),
            on_joined=lambda rid, rn, lid=link_id: self._handle_joined(lid, rid, rn),
            on_room_deleted=lambda rid, lid=link_id: self._handle_room_deleted(lid, rid),
            on_connected=_connected,
            on_disconnected=lambda reason, lid=link_id: self._handle_disconnect(lid, reason),
            on_error=lambda m, ec, lid=link_id: self._on_error and self._on_error(lid, m, ec),
            on_tap_received=lambda d, lid=link_id: self._handle_tap_received(lid, d),
            on_tap_chat=lambda d, lid=link_id: self._handle_tap_chat(lid, d),
            on_tap_open=lambda tid, lid=link_id: self._handle_tap_open(lid, tid),
            on_tap_end=lambda tid, lid=link_id: self._handle_tap_end(lid, tid),
            listen_muted_getter=lambda lid=link_id: (
                self._links[lid].listen_muted if lid in self._links else True
            ),
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
        session.connect(host, port, password=password, server_operator=server_operator)
        return link_id

    def is_server_operator(self, link_id: str) -> bool:
        session = self._sessions.get(link_id)
        if session and session.is_server_operator:
            return True
        link = self._links.get(link_id)
        return bool(link and link.is_server_operator)

    def can_delete_room(self, link_id: str, room_meta: dict) -> bool:
        session = self._sessions.get(link_id)
        if not session:
            return False
        creator_id = str(room_meta.get("creator_id", ""))
        if not creator_id or creator_id == session.client_id:
            return True
        return self.is_server_operator(link_id)

    def delete_room_needs_host_password(self, link_id: str, room_meta: dict) -> bool:
        if not self.is_server_operator(link_id):
            return False
        session = self._sessions.get(link_id)
        if not session:
            return False
        creator_id = str(room_meta.get("creator_id", ""))
        if not creator_id or creator_id == session.client_id:
            return False
        return session.host_password_protected

    def _handle_disconnect(self, link_id: str, reason: str) -> None:
        self._pending_create_password.pop(link_id, None)
        self._pending_join_password.pop(link_id, None)
        link = self._links.get(link_id)
        was_connected = bool(link and link.connected)
        self._sessions.pop(link_id, None)
        with self._lock:
            self._links.pop(link_id, None)
        self._stop_audio_if_idle()
        if was_connected and self._on_link_disconnected:
            self._on_link_disconnected(link_id, reason)

    def _handle_tap_received(self, link_id: str, data: dict[str, Any]) -> None:
        link = self._links.get(link_id)
        if link and not data.get("self_sent"):
            from_id = str(data.get("from_id", ""))
            link.pending_taps.add(from_id)
        tap_id = str(data.get("tap_id", ""))
        if tap_id and link:
            from_id = str(data.get("from_id", ""))
            target_id = str(data.get("target_id", ""))
            from_name = str(data.get("from_name", "?"))
            target_name = str(data.get("target_name", "?"))
            peer_id = target_id if data.get("self_sent") else from_id
            peer_name = target_name if data.get("self_sent") else from_name
            get_active_tap_chat_store().record_received(
                tap_id=tap_id,
                link_host=link.host,
                link_port=link.port,
                peer_id=peer_id,
                peer_name=peer_name,
                server_label=link.label,
            )
        if self._on_tap_received:
            self._on_tap_received(link_id, data)

    def _handle_tap_chat(self, link_id: str, data: dict[str, Any]) -> None:
        tap_id = str(data.get("tap_id", ""))
        if tap_id:
            get_active_tap_chat_store().append_message(
                tap_id,
                name=str(data.get("name", "?")),
                text=str(data.get("text", "")),
            )
        if self._on_tap_chat:
            self._on_tap_chat(link_id, data)

    def _handle_tap_open(self, link_id: str, tap_id: str) -> None:
        if self._on_tap_open:
            self._on_tap_open(link_id, tap_id)

    def _handle_tap_end(self, link_id: str, tap_id: str) -> None:
        get_active_tap_chat_store().remove(tap_id)
        if self._on_tap_end:
            self._on_tap_end(link_id, tap_id)

    def clear_active_tap_chat(self, tap_id: str, *, link_id: str | None = None) -> None:
        """End tap on server when connected and remove persisted thread."""
        store = get_active_tap_chat_store()
        chat = store.get(tap_id)
        target_link = link_id
        if not target_link and chat:
            for lid, link in self._links.items():
                if link.host == chat.link_host and link.port == chat.link_port:
                    target_link = lid
                    break
        if target_link and self._sessions.get(target_link):
            self.end_tap(target_link, tap_id)
        store.remove(tap_id)

    def restore_active_tap_ids(
        self,
        link_id: str,
        participants: list[dict[str, Any]] | None = None,
    ) -> dict[tuple[str, str], str]:
        link = self._links.get(link_id)
        if not link:
            return {}
        return get_active_tap_chat_store().tap_ids_for_server(
            link_id,
            host=link.host,
            port=link.port,
            participants=participants,
        )

    def disconnect(self, link_id: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.disconnect()
            return
        self._sessions.pop(link_id, None)
        with self._lock:
            self._links.pop(link_id, None)
        self._stop_audio_if_idle()

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

    def set_input_volume(self, volume: float) -> None:
        self._settings.input_volume = max(0.0, min(2.0, volume))
        save_settings(self._settings)
        if self._mic:
            self._mic.set_input_volume(self._settings.input_volume)

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

    def set_audio_route(self, route: str) -> None:
        """Hot-swap Android speaker/earpiece/Bluetooth (no-op on desktop)."""
        if platform_name() != "android":
            return
        from babblecast.audio.android_routing import normalize_audio_route

        route = normalize_audio_route(route)
        self._settings.android_audio_route = route
        save_settings(self._settings)
        if self._speaker and hasattr(self._speaker, "set_route"):
            self._speaker.set_route(route, mic_restart_cb=self._restart_mic_if_running)
        self._notify_audio_route_changed(route)

    def list_audio_routes(self) -> list[tuple[str, str, bool]]:
        if platform_name() != "android":
            return []
        from babblecast.audio.android_routing import get_android_router

        return get_android_router().list_routes()

    def _restart_mic_if_running(self) -> None:
        if self._mic and getattr(self._mic, "running", False):
            try:
                self._mic.restart()
            except Exception:
                logger.exception("Mic restart after route change failed")

    def set_master_output_volume(self, volume: float) -> None:
        self._settings.output_volume = max(0.0, min(2.0, volume))
        save_settings(self._settings)
        if self._speaker:
            self._speaker.set_master_volume(self._settings.output_volume)

    @property
    def local_mic_level(self) -> float:
        return self._local_mic_level

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

    def _handle_joined(self, link_id: str, room_id: str, room_name: str) -> None:
        pending_create = self._pending_create_password.pop(link_id, None)
        if pending_create and pending_create[0] == room_name.strip():
            self._remember_room_password(link_id, room_id, pending_create[1])
        else:
            pending_join = self._pending_join_password.pop(link_id, None)
            if pending_join and pending_join[0] == room_id:
                self._remember_room_password(link_id, room_id, pending_join[1])
        if self._on_joined:
            self._on_joined(link_id, room_id, room_name)

    def _handle_room_deleted(self, link_id: str, room_id: str) -> None:
        self._forget_room_password(link_id, room_id)
        if self._on_room_deleted:
            self._on_room_deleted(link_id, room_id)

    def _remember_room_password(self, link_id: str, room_id: str, password: str) -> None:
        link = self._links.get(link_id)
        if not link:
            return
        remember_room_password(self._settings, link.host, link.port, room_id, password)

    def _forget_room_password(self, link_id: str, room_id: str) -> None:
        link = self._links.get(link_id)
        if not link:
            return
        forget_room_password(self._settings, link.host, link.port, room_id)

    def get_remembered_room_password(self, link_id: str, room_id: str) -> str:
        link = self._links.get(link_id)
        if not link:
            return ""
        return get_room_password(self._settings, link.host, link.port, room_id)

    def admin_room_password_display(self, link_id: str) -> tuple[bool, str]:
        session = self._sessions.get(link_id)
        if not session or not session.room_id:
            return False, ""
        room_meta = session.room_by_id(session.room_id)
        pwd = self.get_remembered_room_password(link_id, session.room_id)
        return room_password_admin_display(room_meta, remembered_password=pwd)

    def create_room(self, link_id: str, name: str, *, password: str = "") -> None:
        session = self._sessions.get(link_id)
        if session:
            pwd = password.strip()
            if pwd:
                self._pending_create_password[link_id] = (name.strip(), pwd)
            session.create_room(name, password=password)

    def delete_room(self, link_id: str, room_id: str, *, host_password: str = "") -> None:
        session = self._sessions.get(link_id)
        if session:
            session.delete_room(room_id, host_password=host_password)

    def join_room(self, link_id: str, room_id: str, *, password: str = "") -> None:
        session = self._sessions.get(link_id)
        if session:
            pwd = password.strip()
            if pwd:
                self._pending_join_password[link_id] = (room_id, pwd)
            session.join_room(room_id, password=password)

    def request_rooms(self, link_id: str) -> None:
        session = self._sessions.get(link_id)
        if session:
            session.request_rooms()

    @property
    def speaker(self):
        return self._speaker
