"""Client connection session — WebSocket control + UDP voice."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
from collections.abc import Callable
from typing import Any

import websockets

from babblecast.audio.codec import OpusCodec
from babblecast.audio.factory import create_mic, create_speaker
from babblecast.audio.jitter import VoiceJitterBuffer
from babblecast.audio.processing import NoiseGate, NoiseSuppressor
from babblecast.constants import FRAME_BYTES, composite_participant_key
from babblecast.config import UserSettings, get_settings, save_settings
from babblecast.protocol import MsgType, VoicePacket, decode_msg, encode_msg, new_id, parse_error_code

logger = logging.getLogger(__name__)


class ClientSession:
    def __init__(
        self,
        on_presence: Callable[[str, list[dict]], None] | None = None,
        on_chat: Callable[[dict], None] | None = None,
        on_rooms: Callable[[list[dict]], None] | None = None,
        on_joined: Callable[[str, str], None] | None = None,
        on_room_deleted: Callable[[str], None] | None = None,
        on_connected: Callable[[], None] | None = None,
        on_disconnected: Callable[[str], None] | None = None,
        on_error: Callable[[str, str | None], None] | None = None,
        on_tap_received: Callable[[dict], None] | None = None,
        on_tap_chat: Callable[[dict], None] | None = None,
        on_tap_open: Callable[[str], None] | None = None,
        on_tap_end: Callable[[str], None] | None = None,
        *,
        link_id: str = "",
        bridge_speaker: Any | None = None,
        listen_muted_getter: Callable[[], bool] | None = None,
    ) -> None:
        self._on_presence = on_presence
        self._on_chat = on_chat
        self._on_rooms = on_rooms
        self._on_joined = on_joined
        self._on_room_deleted = on_room_deleted
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._on_tap_received = on_tap_received
        self._on_tap_chat = on_tap_chat
        self._on_tap_open = on_tap_open
        self._on_tap_end = on_tap_end
        self._link_id = link_id
        self._bridge_speaker = bridge_speaker
        self._listen_muted_getter = listen_muted_getter
        self._bridge_mic_muted = False
        self._settings = get_settings()
        self._client_id = new_id()
        self._room_id: str | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._udp_sock: socket.socket | None = None
        self._udp_thread: threading.Thread | None = None
        self._udp_port = 0
        self._server_udp_port = 8766
        self._sequence = 0
        self._codec = OpusCodec()
        self._gate = NoiseGate(threshold_db=self._settings.gate_threshold_db)
        self._suppressor = NoiseSuppressor(strength=self._settings.noise_suppression)
        self._mic = None
        self._speaker = None
        self._host = ""
        self._ws_port = 8765
        self._password = ""
        self._server_name = ""
        self._user_disconnect = False
        self._audio_started = False
        self._welcomed = False
        self._last_level_sent = 0.0
        self._jitter: dict[str, VoiceJitterBuffer] = {}
        self._jitter_lock = threading.Lock()
        self._codec_lock = threading.Lock()

    @property
    def link_id(self) -> str:
        return self._link_id

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def room_id(self) -> str | None:
        return self._room_id

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def connected(self) -> bool:
        return self._running and self._ws is not None

    @property
    def is_bridge(self) -> bool:
        return bool(self._link_id and self._bridge_speaker is not None)

    def set_bridge_mic_muted(self, muted: bool) -> None:
        self._bridge_mic_muted = muted

    def _participant_key(self, client_id: str) -> str:
        if self._link_id:
            return composite_participant_key(self._link_id, client_id)
        return client_id

    def _setup_audio(self) -> None:
        if self.is_bridge:
            return
        self._mic = create_mic(
            device_key=self._settings.input_device,
            gate=self._gate,
            suppressor=self._suppressor,
            on_frame=self._on_audio_frame,
            on_level=self._on_voice_level,
        )
        self._mic.set_input_volume(self._settings.input_volume)
        self._speaker = create_speaker(
            device_key=self._settings.output_device,
            master_volume=self._settings.output_volume,
        )
        for uid, vol in self._settings.per_user_volumes.items():
            self._speaker.set_participant_volume(uid, vol)
        for uid, muted in self._settings.per_user_muted.items():
            self._speaker.set_participant_muted(uid, muted)
        self._mic.set_input_volume(self._settings.input_volume)

    def send_voice_pcm(self, pcm: bytes) -> None:
        if self._bridge_mic_muted or not self._room_id or not self._udp_sock:
            return
        if len(pcm) != FRAME_BYTES:
            return
        with self._codec_lock:
            opus = self._codec.encode(pcm)
        if not opus:
            return
        self._sequence += 1
        packet = VoicePacket(
            room_id=self._room_id,
            sender_id=self._client_id,
            sequence=self._sequence,
            opus_payload=opus,
        )
        try:
            self._udp_sock.sendto(packet.encode(), (self._host, self._server_udp_port))
        except OSError:
            pass

    def send_voice_level(self, level: float) -> None:
        if self._bridge_mic_muted:
            return
        self._on_voice_level(level)

    def _on_audio_frame(self, pcm: bytes, _level: float) -> None:
        self.send_voice_pcm(pcm)

    def _on_voice_level(self, level: float) -> None:
        if not self._loop or not self._ws:
            return
        if abs(level - self._last_level_sent) < 0.04 and (level > 0.05) == (self._last_level_sent > 0.05):
            return
        self._last_level_sent = level
        asyncio.run_coroutine_threadsafe(
            self._send(encode_msg(MsgType.VOICE_LEVEL, level=level)),
            self._loop,
        )

    def _start_udp(self) -> None:
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp_sock.bind(("0.0.0.0", 0))
        self._udp_port = self._udp_sock.getsockname()[1]
        self._udp_thread = threading.Thread(target=self._udp_recv_loop, daemon=True, name="bbc-udp-recv")
        self._udp_thread.start()

    def _udp_recv_loop(self) -> None:
        assert self._udp_sock is not None
        while self._running:
            try:
                self._udp_sock.settimeout(0.5)
                data, _ = self._udp_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if self._listen_muted_getter and self._listen_muted_getter():
                continue
            packet = VoicePacket.decode(data)
            if not packet or packet.sender_id == self._client_id:
                continue
            with self._jitter_lock:
                jb = self._jitter.setdefault(packet.sender_id, VoiceJitterBuffer())
            payloads = jb.push(packet.sequence, packet.opus_payload)
            speaker = self._bridge_speaker if self.is_bridge else self._speaker
            if not speaker:
                continue
            key = self._participant_key(packet.sender_id)
            for payload in payloads:
                with self._codec_lock:
                    if payload is None:
                        pcm = self._codec.decode_plc()
                    else:
                        pcm = self._codec.decode(payload)
                if len(pcm) == FRAME_BYTES:
                    speaker.push_pcm(key, pcm)

    async def _send(self, message: str) -> None:
        if self._ws:
            await self._ws.send(message)

    async def _handle(self, data: dict[str, Any]) -> None:
        mtype = data.get("type")
        if mtype == MsgType.WELCOME:
            self._welcomed = True
            self._client_id = str(data.get("client_id", self._client_id))
            self._room_id = str(data.get("room_id", ""))
            self._server_name = str(data.get("server_name", ""))
            self._server_udp_port = int(data.get("udp_port", 8766))
            await self._send(
                encode_msg("udp_endpoint", host=self._local_ip(), port=self._udp_port)
            )
            self._start_audio()
            if self._on_joined and self._room_id:
                self._on_joined(self._room_id, str(data.get("room_name", "General")))
            if self._on_connected:
                self._on_connected()
            return
        if mtype == MsgType.PRESENCE:
            if self._on_presence:
                self._on_presence(str(data.get("room_id", "")), list(data.get("participants", [])))
            return
        if mtype == MsgType.CHAT:
            if self._on_chat:
                self._on_chat(data)
            return
        if mtype == MsgType.ROOMS:
            if self._on_rooms:
                self._on_rooms(list(data.get("rooms", [])))
            return
        if mtype == MsgType.JOINED:
            self._room_id = str(data.get("room_id", ""))
            if self._on_joined and self._room_id:
                self._on_joined(self._room_id, str(data.get("room_name", "Room")))
            return
        if mtype == MsgType.ROOM_DELETED:
            if self._on_room_deleted:
                self._on_room_deleted(str(data.get("room_id", "")))
            return
        if mtype == MsgType.TAP_RECEIVED:
            if self._on_tap_received:
                self._on_tap_received(data)
            return
        if mtype == MsgType.TAP_OPEN:
            if self._on_tap_open:
                self._on_tap_open(str(data.get("tap_id", "")))
            return
        if mtype == MsgType.TAP_CHAT:
            if self._on_tap_chat:
                self._on_tap_chat(data)
            return
        if mtype == MsgType.TAP_END:
            if self._on_tap_end:
                self._on_tap_end(str(data.get("tap_id", "")))
            return
        if mtype == MsgType.ERROR:
            message = str(data.get("message", "Unknown error"))
            error_code = parse_error_code(data)
            if self._on_error:
                self._on_error(message, error_code)
            if not self._welcomed and self._ws:
                await self._ws.close(1008, message)
            return

    def _start_audio(self) -> None:
        if self._audio_started or self.is_bridge:
            return
        try:
            if self._speaker:
                self._speaker.start()
            if self._mic:
                self._mic.start()
            self._audio_started = True
        except Exception as exc:
            logger.exception("Failed to start audio devices")
            if self._mic:
                self._mic.stop()
            if self._speaker:
                self._speaker.stop()
            self._audio_started = False
            if self._on_error:
                self._on_error(f"Audio unavailable: {exc}", None)

    def _stop_audio(self) -> None:
        if self.is_bridge:
            return
        if self._mic:
            self._mic.stop()
        if self._speaker:
            self._speaker.stop()
        self._audio_started = False

    def _local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((self._host, self._ws_port))
                return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    async def _run_ws(self) -> None:
        uri = f"ws://{self._host}:{self._ws_port}"
        name = self._settings.display_name.strip() or socket.gethostname()
        hello_payload: dict[str, Any] = {"name": name, "client_id": self._client_id}
        if self._password:
            hello_payload["password"] = self._password
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            self._ws = ws
            await ws.send(encode_msg(MsgType.HELLO, **hello_payload))
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = decode_msg(raw)
                except (ValueError, TypeError):
                    continue
                await self._handle(msg)

    def _shutdown_transport(self, *, close_ws: bool = True) -> None:
        """Stop network/audio I/O without firing disconnect callbacks."""
        self._running = False
        self._stop_audio()
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except OSError:
                pass
            self._udp_sock = None
        if self._udp_thread:
            self._udp_thread.join(timeout=2)
            self._udp_thread = None
        with self._jitter_lock:
            self._jitter.clear()
        if close_ws and self._loop and self._ws and threading.current_thread() is not self._thread:
            try:
                asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop).result(timeout=2)
            except Exception:
                pass
        self._ws = None

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        disconnect_reason = ""
        try:
            self._loop.run_until_complete(self._run_ws())
        except Exception as exc:
            if self._welcomed:
                logger.exception("WebSocket session ended")
            else:
                logger.info("Connection closed before welcome: %s", exc)
            disconnect_reason = str(exc)
        finally:
            self._shutdown_transport(close_ws=False)
            if self._loop:
                self._loop.close()
            self._loop = None
            if self._on_disconnected and not self._user_disconnect:
                self._on_disconnected(disconnect_reason or "Connection closed")

    def connect(self, host: str, ws_port: int = 8765, password: str = "") -> None:
        if self._running:
            self.disconnect()
        self._user_disconnect = False
        self._welcomed = False
        self._host = host
        self._ws_port = ws_port
        self._password = password
        if not self.is_bridge:
            self._settings.last_server_host = host
            self._settings.last_server_port = ws_port
            save_settings(self._settings)
        self._setup_audio()
        self._running = True
        self._start_udp()
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="bbc-ws-client")
        self._thread.start()

    def disconnect(self, *, notify: bool = True) -> None:
        if not self._running and not self._thread:
            return
        self._user_disconnect = True
        self._shutdown_transport()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        if notify and self._on_disconnected:
            self._on_disconnected("Disconnected")

    def set_muted(self, muted: bool) -> None:
        if self._mic:
            self._mic.muted = muted
        self._send_async(encode_msg(MsgType.MUTE, target_id=None, muted=muted))

    def set_ptt(self, active: bool) -> None:
        if self._mic:
            self._mic.ptt_active = active
        self._send_async(encode_msg(MsgType.PTT, active=active))

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

    def set_participant_volume(self, client_id: str, volume: float) -> None:
        key = self._participant_key(client_id)
        self._settings.per_user_volumes[key] = volume
        save_settings(self._settings)
        speaker = self._bridge_speaker if self.is_bridge else self._speaker
        if speaker:
            speaker.set_participant_volume(key, volume)
        self._send_async(encode_msg(MsgType.VOLUME, target_id=client_id, volume=volume))

    def set_participant_muted(self, client_id: str, muted: bool) -> None:
        key = self._participant_key(client_id)
        self._settings.per_user_muted[key] = muted
        save_settings(self._settings)
        speaker = self._bridge_speaker if self.is_bridge else self._speaker
        if speaker:
            speaker.set_participant_muted(key, muted)
        self._send_async(encode_msg(MsgType.MUTE, target_id=client_id, muted=muted))

    def send_chat(self, text: str) -> None:
        self._send_async(encode_msg(MsgType.CHAT, text=text))

    def send_tap(self, target_id: str, text: str = "") -> None:
        self._send_async(encode_msg(MsgType.TAP, target_id=target_id, text=text))

    def open_tap(self, tap_id: str) -> None:
        self._send_async(encode_msg(MsgType.TAP_OPEN, tap_id=tap_id))

    def send_tap_chat(self, tap_id: str, text: str) -> None:
        self._send_async(encode_msg(MsgType.TAP_CHAT, tap_id=tap_id, text=text))

    def end_tap(self, tap_id: str) -> None:
        self._send_async(encode_msg(MsgType.TAP_END, tap_id=tap_id))

    def create_room(self, name: str) -> None:
        self._send_async(encode_msg(MsgType.CREATE_ROOM, name=name))

    def delete_room(self, room_id: str) -> None:
        self._send_async(encode_msg(MsgType.DELETE_ROOM, room_id=room_id))

    def join_room(self, room_id: str) -> None:
        self._send_async(encode_msg(MsgType.JOIN_ROOM, room_id=room_id))

    def request_rooms(self) -> None:
        self._send_async(encode_msg(MsgType.ROOM_LIST))

    def _send_async(self, message: str) -> None:
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._send(message), self._loop)

    def update_settings(self, settings: UserSettings) -> None:
        self._settings = settings
