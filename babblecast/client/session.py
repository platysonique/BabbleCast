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
from babblecast.audio.engine import MicCapture, SpeakerOutput
from babblecast.audio.processing import NoiseGate, NoiseSuppressor
from babblecast.config import UserSettings, get_settings, save_settings
from babblecast.protocol import MsgType, VoicePacket, decode_msg, encode_msg, new_id

logger = logging.getLogger(__name__)


class ClientSession:
    def __init__(
        self,
        on_presence: Callable[[str, list[dict]], None] | None = None,
        on_chat: Callable[[dict], None] | None = None,
        on_rooms: Callable[[list[dict]], None] | None = None,
        on_connected: Callable[[], None] | None = None,
        on_disconnected: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._on_presence = on_presence
        self._on_chat = on_chat
        self._on_rooms = on_rooms
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
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
        self._mic: MicCapture | None = None
        self._speaker: SpeakerOutput | None = None
        self._host = ""
        self._ws_port = 8765
        self._user_disconnect = False
        self._audio_started = False
        self._last_level_sent = 0.0

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def room_id(self) -> str | None:
        return self._room_id

    @property
    def connected(self) -> bool:
        return self._running and self._ws is not None

    def _setup_audio(self) -> None:
        self._mic = MicCapture(
            device_key=self._settings.input_device,
            gate=self._gate,
            suppressor=self._suppressor,
            on_frame=self._on_audio_frame,
            on_level=self._on_voice_level,
        )
        self._speaker = SpeakerOutput(
            device_key=self._settings.output_device,
            master_volume=self._settings.output_volume,
        )
        for uid, vol in self._settings.per_user_volumes.items():
            self._speaker.set_participant_volume(uid, vol)
        for uid, muted in self._settings.per_user_muted.items():
            self._speaker.set_participant_muted(uid, muted)

    def _on_audio_frame(self, pcm: bytes, _level: float) -> None:
        if not self._room_id or not self._udp_sock:
            return
        try:
            opus = self._codec.encode(pcm)
        except Exception:
            logger.exception("Opus encode failed")
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
            packet = VoicePacket.decode(data)
            if not packet or packet.sender_id == self._client_id:
                continue
            try:
                pcm = self._codec.decode(packet.opus_payload)
            except Exception:
                continue
            if self._speaker:
                self._speaker.push_pcm(packet.sender_id, pcm)

    async def _send(self, message: str) -> None:
        if self._ws:
            await self._ws.send(message)

    async def _handle(self, data: dict[str, Any]) -> None:
        mtype = data.get("type")
        if mtype == MsgType.WELCOME:
            self._client_id = str(data.get("client_id", self._client_id))
            self._room_id = str(data.get("room_id", ""))
            self._server_udp_port = int(data.get("udp_port", 8766))
            await self._send(
                encode_msg("udp_endpoint", host=self._local_ip(), port=self._udp_port)
            )
            self._start_audio()
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
            return
        if mtype == MsgType.ERROR:
            if self._on_error:
                self._on_error(str(data.get("message", "Unknown error")))
            return

    def _start_audio(self) -> None:
        if self._audio_started:
            return
        try:
            if self._mic:
                self._mic.start()
            if self._speaker:
                self._speaker.start()
            self._audio_started = True
        except Exception as exc:
            logger.exception("Failed to start audio devices")
            if self._on_error:
                self._on_error(f"Audio unavailable: {exc}")

    def _stop_audio(self) -> None:
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
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            self._ws = ws
            await ws.send(encode_msg(MsgType.HELLO, name=name, client_id=self._client_id))
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = decode_msg(raw)
                except (ValueError, TypeError):
                    continue
                await self._handle(msg)

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_ws())
        except Exception as exc:
            logger.exception("WebSocket session ended")
            if self._on_disconnected and not self._user_disconnect:
                self._on_disconnected(str(exc))
        finally:
            self._running = False
            self._ws = None
            if self._loop:
                self._loop.close()
            self._loop = None

    def connect(self, host: str, ws_port: int = 8765) -> None:
        if self._running:
            self.disconnect()
        self._user_disconnect = False
        self._host = host
        self._ws_port = ws_port
        self._settings.last_server_host = host
        self._settings.last_server_port = ws_port
        save_settings(self._settings)
        self._setup_audio()
        self._start_udp()
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="bbc-ws-client")
        self._thread.start()

    def disconnect(self) -> None:
        if not self._running and not self._thread:
            return
        self._user_disconnect = True
        self._running = False
        self._stop_audio()
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except OSError:
                pass
            self._udp_sock = None
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        if self._on_disconnected:
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
        self._settings.per_user_volumes[client_id] = volume
        save_settings(self._settings)
        if self._speaker:
            self._speaker.set_participant_volume(client_id, volume)
        self._send_async(encode_msg(MsgType.VOLUME, target_id=client_id, volume=volume))

    def set_participant_muted(self, client_id: str, muted: bool) -> None:
        self._settings.per_user_muted[client_id] = muted
        save_settings(self._settings)
        if self._speaker:
            self._speaker.set_participant_muted(client_id, muted)
        self._send_async(encode_msg(MsgType.MUTE, target_id=client_id, muted=muted))

    def send_chat(self, text: str) -> None:
        self._send_async(encode_msg(MsgType.CHAT, text=text))

    def create_room(self, name: str) -> None:
        self._send_async(encode_msg(MsgType.CREATE_ROOM, name=name))

    def join_room(self, room_id: str) -> None:
        self._send_async(encode_msg(MsgType.JOIN_ROOM, room_id=room_id))

    def request_rooms(self) -> None:
        self._send_async(encode_msg(MsgType.ROOM_LIST))

    def _send_async(self, message: str) -> None:
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._send(message), self._loop)

    def update_settings(self, settings: UserSettings) -> None:
        self._settings = settings
