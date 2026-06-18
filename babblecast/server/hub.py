"""Async BabbleCast hub — rooms, chat, presence, voice relay."""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from babblecast.constants import DEFAULT_UDP_PORT, DEFAULT_WS_PORT, WS_PING_INTERVAL_SEC, WS_PING_TIMEOUT_SEC
from babblecast.discovery import ServerAdvertiser
from babblecast.network import advertise_hosts_for_settings
from babblecast.server.auth import check_password, make_password_verifier
from babblecast.protocol import (
    ErrorCode,
    MsgType,
    Participant,
    RoomInfo,
    VoicePacket,
    clamp_chat,
    clamp_name,
    clamp_room_name,
    decode_msg,
    encode_msg,
    new_id,
)

logger = logging.getLogger(__name__)

# Port-scan probes open a bare TCP socket; websockets logs each failed handshake
# at ERROR with a full traceback. Keep real BabbleCast logs on babblecast.* only.
_ws_probe_logger = logging.getLogger("babblecast.ws")
_ws_probe_logger.setLevel(logging.CRITICAL)

_VOICE_PRESENCE_INTERVAL_SEC = 0.1
_VOICE_LEVEL_DELTA = 0.05


@dataclass
class ClientState:
    ws: WebSocketServerProtocol
    client_id: str
    name: str
    room_id: str | None = None
    muted: bool = False
    ptt_active: bool = False
    voice_level: float = 0.0
    volume: float = 1.0
    speaking: bool = False
    is_server_operator: bool = False
    udp_addr: tuple[str, int] | None = None
    udp_source: tuple[str, int] | None = None
    last_presence_at: float = 0.0

    def participant(self) -> Participant:
        return Participant(
            client_id=self.client_id,
            name=self.name,
            muted=self.muted,
            ptt_active=self.ptt_active,
            voice_level=self.voice_level,
            volume=self.volume,
            speaking=self.speaking,
        )


@dataclass
class Room:
    room_id: str
    name: str
    members: set[str] = field(default_factory=set)
    creator_id: str = ""
    password_salt: str = ""
    password_digest: str = ""


@dataclass
class TapSession:
    tap_id: str
    initiator_id: str
    target_id: str
    opened: bool = False


class BabbleCastHub:
    def __init__(
        self,
        host: str = "0.0.0.0",
        ws_port: int = DEFAULT_WS_PORT,
        udp_port: int = DEFAULT_UDP_PORT,
        server_name: str = "BabbleCast",
        advertise: bool = True,
        server_password: str = "",
    ) -> None:
        self.host = host
        self.ws_port = ws_port
        self.udp_port = udp_port
        self.server_name = server_name
        self.advertise = advertise
        self._password_salt = ""
        self._password_digest = ""
        if server_password.strip():
            self._password_salt, self._password_digest = make_password_verifier(server_password.strip())
        self._clients: dict[str, ClientState] = {}
        self._rooms: dict[str, Room] = {}
        self._tap_sessions: dict[str, TapSession] = {}
        self._ws_server = None
        self._udp_transport = None
        self._advertiser: ServerAdvertiser | None = None
        self._beacon = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._join_lock = asyncio.Lock()

    @property
    def password_protected(self) -> bool:
        return bool(self._password_digest)

    def _default_room(self) -> Room:
        for room in self._rooms.values():
            return room
        room = Room(room_id=new_id(), name="General")
        self._rooms[room.room_id] = room
        return room

    def _display_name_taken(self, name: str, *, exclude_id: str | None = None) -> bool:
        key = name.casefold()
        for cid, client in self._clients.items():
            if cid == exclude_id:
                continue
            if client.name.casefold() == key:
                return True
        return False

    def _connection_is_server_operator(self, ws: WebSocketServerProtocol, hello: dict[str, Any]) -> bool:
        """Host claim — only trusted for connections from this machine."""
        if not hello.get("server_operator"):
            return False
        try:
            remote = str(ws.remote_address[0]) if ws.remote_address else ""
        except (AttributeError, IndexError, TypeError):
            return False
        if remote in ("127.0.0.1", "::1"):
            return True
        local_ips = set(advertise_hosts_for_settings())
        if self.host not in ("0.0.0.0", "", "127.0.0.1"):
            local_ips.add(self.host)
        return remote in local_ips

    def _register_udp_source(self, client: ClientState, addr: tuple[str, int]) -> bool:
        """Verify datagram source for voice packets from this client."""
        if client.udp_addr is None:
            return False
        if addr[1] != client.udp_addr[1]:
            return False
        if client.udp_source is None:
            client.udp_source = addr
            return True
        return client.udp_source == addr

    async def _broadcast_room(self, room_id: str, message: str, skip: str | None = None) -> None:
        room = self._rooms.get(room_id)
        if not room:
            return
        tasks = []
        for cid in room.members:
            if cid == skip:
                continue
            client = self._clients.get(cid)
            if client:
                tasks.append(client.ws.send(message))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_presence(self, room_id: str) -> None:
        room = self._rooms.get(room_id)
        if not room:
            return
        participants = []
        for cid in room.members:
            c = self._clients.get(cid)
            if c:
                participants.append(c.participant().to_dict())
        msg = encode_msg(MsgType.PRESENCE, room_id=room_id, participants=participants)
        await self._broadcast_room(room_id, msg)

    def _room_info(self, room: Room) -> dict[str, Any]:
        return RoomInfo(
            room.room_id,
            room.name,
            len(room.members),
            password_protected=bool(room.password_digest),
            creator_id=room.creator_id,
        ).to_dict()

    async def _send_rooms(self, client: ClientState) -> None:
        rooms = [self._room_info(r) for r in self._rooms.values()]
        await client.ws.send(encode_msg(MsgType.ROOMS, rooms=rooms))

    async def _handle_message(self, client: ClientState, data: dict[str, Any]) -> None:
        mtype = data.get("type")

        if mtype == MsgType.PING:
            await client.ws.send(encode_msg(MsgType.PONG))
            return

        if mtype == MsgType.ROOM_LIST:
            await self._send_rooms(client)
            return

        if mtype == MsgType.CREATE_ROOM:
            name = clamp_room_name(str(data.get("name", "Room")))
            password = str(data.get("password", "")).strip()
            salt = ""
            digest = ""
            if password:
                salt, digest = make_password_verifier(password)
            room = Room(
                room_id=new_id(),
                name=name,
                creator_id=client.client_id,
                password_salt=salt,
                password_digest=digest,
            )
            self._rooms[room.room_id] = room
            if client.room_id:
                old = self._rooms.get(client.room_id)
                if old:
                    old.members.discard(client.client_id)
                    await self._send_presence(client.room_id)
            client.room_id = room.room_id
            room.members.add(client.client_id)
            await client.ws.send(
                encode_msg(MsgType.ROOM_CREATED, room=self._room_info(room))
            )
            await client.ws.send(
                encode_msg(MsgType.JOINED, room_id=room.room_id, room_name=room.name)
            )
            await self._send_presence(room.room_id)
            await self._broadcast_all_rooms()
            return

        if mtype == MsgType.JOIN_ROOM:
            room_id = str(data.get("room_id", ""))
            room = self._rooms.get(room_id)
            if not room:
                await client.ws.send(
                    encode_msg(
                        MsgType.ERROR,
                        message="Room not found",
                        error_code=ErrorCode.ROOM_NOT_FOUND.value,
                    )
                )
                return
            if room.password_digest and not client.is_server_operator:
                supplied = str(data.get("password", ""))
                if not supplied:
                    await client.ws.send(
                        encode_msg(
                            MsgType.ERROR,
                            message="Room password required",
                            error_code=ErrorCode.ROOM_PASSWORD_REQUIRED.value,
                        )
                    )
                    return
                if not check_password(supplied, room.password_salt, room.password_digest):
                    await client.ws.send(
                        encode_msg(
                            MsgType.ERROR,
                            message="Incorrect room password",
                            error_code=ErrorCode.ROOM_PASSWORD_WRONG.value,
                        )
                    )
                    return
            if client.room_id:
                old = self._rooms.get(client.room_id)
                if old:
                    old.members.discard(client.client_id)
                    await self._send_presence(client.room_id)
            client.room_id = room_id
            room.members.add(client.client_id)
            await client.ws.send(encode_msg(MsgType.JOINED, room_id=room_id, room_name=room.name))
            await self._send_presence(room_id)
            await self._broadcast_all_rooms()
            return

        if mtype == MsgType.DELETE_ROOM:
            room_id = str(data.get("room_id", ""))
            room = self._rooms.get(room_id)
            if not room:
                await client.ws.send(
                    encode_msg(
                        MsgType.ERROR,
                        message="Room not found",
                        error_code=ErrorCode.ROOM_NOT_FOUND.value,
                    )
                )
                return
            if room.creator_id and room.creator_id != client.client_id:
                if not client.is_server_operator:
                    await client.ws.send(
                        encode_msg(
                            MsgType.ERROR,
                            message="Only the room creator can delete this room",
                            error_code=ErrorCode.NOT_ROOM_OWNER.value,
                        )
                    )
                    return
                if self._password_digest:
                    supplied = str(data.get("host_password", ""))
                    if not supplied:
                        await client.ws.send(
                            encode_msg(
                                MsgType.ERROR,
                                message="Host password required to delete",
                                error_code=ErrorCode.PASSWORD_REQUIRED.value,
                            )
                        )
                        return
                    if not check_password(supplied, self._password_salt, self._password_digest):
                        await client.ws.send(
                            encode_msg(
                                MsgType.ERROR,
                                message="Incorrect host password",
                                error_code=ErrorCode.PASSWORD_WRONG.value,
                            )
                        )
                        return
            if len(self._rooms) <= 1:
                await client.ws.send(
                    encode_msg(
                        MsgType.ERROR,
                        message="Cannot delete the last room",
                        error_code=ErrorCode.LAST_ROOM.value,
                    )
                )
                return
            fallback = next(r for rid, r in self._rooms.items() if rid != room_id)
            members = list(room.members)
            for cid in members:
                member = self._clients.get(cid)
                if not member:
                    continue
                member.room_id = fallback.room_id
                fallback.members.add(cid)
                await member.ws.send(
                    encode_msg(
                        MsgType.JOINED,
                        room_id=fallback.room_id,
                        room_name=fallback.name,
                    )
                )
            del self._rooms[room_id]
            deleted_msg = encode_msg(MsgType.ROOM_DELETED, room_id=room_id)
            for c in self._clients.values():
                await c.ws.send(deleted_msg)
            await self._send_presence(fallback.room_id)
            await self._broadcast_all_rooms()
            return

        if mtype == MsgType.LEAVE_ROOM:
            if client.room_id:
                room = self._rooms.get(client.room_id)
                if room:
                    room.members.discard(client.client_id)
                    rid = client.room_id
                    client.room_id = None
                    await self._send_presence(rid)
            await self._broadcast_all_rooms()
            return

        if mtype == MsgType.CHAT:
            if not client.room_id:
                return
            text = clamp_chat(str(data.get("text", "")))
            if not text:
                return
            msg = encode_msg(
                MsgType.CHAT,
                room_id=client.room_id,
                client_id=client.client_id,
                name=client.name,
                text=text,
                ts=asyncio.get_event_loop().time(),
            )
            await self._broadcast_room(client.room_id, msg)
            return

        if mtype == MsgType.PTT:
            client.ptt_active = bool(data.get("active", False))
            if client.room_id:
                await self._send_presence(client.room_id)
            return

        if mtype == MsgType.MUTE:
            target = data.get("target_id")
            muted = bool(data.get("muted", False))
            if target is None or target == client.client_id:
                client.muted = muted
            elif client.room_id:
                target_client = self._clients.get(str(target))
                if target_client and target_client.room_id == client.room_id:
                    target_client.muted = muted
            if client.room_id:
                await self._send_presence(client.room_id)
            return

        if mtype == MsgType.VOLUME:
            target = str(data.get("target_id", ""))
            volume = float(data.get("volume", 1.0))
            if target == client.client_id:
                client.volume = max(0.0, min(2.0, volume))
            elif client.room_id:
                tc = self._clients.get(target)
                if tc and tc.room_id == client.room_id:
                    tc.volume = max(0.0, min(2.0, volume))
            if client.room_id:
                await self._send_presence(client.room_id)
            return

        if mtype == MsgType.VOICE_LEVEL:
            new_level = float(data.get("level", 0.0))
            new_speaking = new_level > 0.08 and not client.muted
            speaking_changed = new_speaking != client.speaking
            level_delta = abs(new_level - client.voice_level)
            client.voice_level = new_level
            client.speaking = new_speaking
            if client.room_id:
                now = time.monotonic()
                if speaking_changed or (
                    level_delta > _VOICE_LEVEL_DELTA
                    and now - client.last_presence_at >= _VOICE_PRESENCE_INTERVAL_SEC
                ):
                    client.last_presence_at = now
                    await self._send_presence(client.room_id)
            return

        if mtype == "udp_endpoint":
            host = str(data.get("host", ""))
            port = int(data.get("port", 0))
            if host and port:
                client.udp_addr = (host, port)
            return

        if mtype == MsgType.TAP:
            target_id = str(data.get("target_id", ""))
            preview = str(data.get("text", ""))[:200]
            target = self._clients.get(target_id)
            if not target:
                await client.ws.send(
                    encode_msg(
                        MsgType.ERROR,
                        message="User not found",
                        error_code=ErrorCode.USER_NOT_FOUND.value,
                    )
                )
                return
            tap_id = new_id()
            self._tap_sessions[tap_id] = TapSession(tap_id, client.client_id, target_id)
            await target.ws.send(
                encode_msg(
                    MsgType.TAP_RECEIVED,
                    tap_id=tap_id,
                    from_id=client.client_id,
                    from_name=client.name,
                    target_id=target_id,
                    target_name=target.name,
                    text=preview,
                )
            )
            await client.ws.send(
                encode_msg(
                    MsgType.TAP_RECEIVED,
                    tap_id=tap_id,
                    from_id=client.client_id,
                    from_name=client.name,
                    target_id=target_id,
                    target_name=target.name,
                    text=preview,
                    self_sent=True,
                )
            )
            return

        if mtype == MsgType.TAP_OPEN:
            tap_id = str(data.get("tap_id", ""))
            session = self._tap_sessions.get(tap_id)
            if not session:
                await client.ws.send(
                    encode_msg(
                        MsgType.ERROR,
                        message="Tap not found",
                        error_code=ErrorCode.TAP_NOT_FOUND.value,
                    )
                )
                return
            if client.client_id not in (session.initiator_id, session.target_id):
                await client.ws.send(
                    encode_msg(
                        MsgType.ERROR,
                        message="Not a tap participant",
                        error_code=ErrorCode.TAP_NOT_PARTICIPANT.value,
                    )
                )
                return
            session.opened = True
            for cid in (session.initiator_id, session.target_id):
                peer = self._clients.get(cid)
                if peer:
                    await peer.ws.send(encode_msg(MsgType.TAP_OPEN, tap_id=tap_id))
            return

        if mtype == MsgType.TAP_CHAT:
            tap_id = str(data.get("tap_id", ""))
            text = clamp_chat(str(data.get("text", "")))
            if not text:
                return
            session = self._tap_sessions.get(tap_id)
            if not session or not session.opened:
                await client.ws.send(
                    encode_msg(
                        MsgType.ERROR,
                        message="Tap not open",
                        error_code=ErrorCode.TAP_NOT_OPEN.value,
                    )
                )
                return
            if client.client_id not in (session.initiator_id, session.target_id):
                return
            other_id = (
                session.target_id
                if client.client_id == session.initiator_id
                else session.initiator_id
            )
            other = self._clients.get(other_id)
            payload = encode_msg(
                MsgType.TAP_CHAT,
                tap_id=tap_id,
                from_id=client.client_id,
                name=client.name,
                text=text,
                ts=asyncio.get_event_loop().time(),
            )
            await client.ws.send(payload)
            if other:
                await other.ws.send(payload)
            return

        if mtype == MsgType.TAP_END:
            tap_id = str(data.get("tap_id", ""))
            session = self._tap_sessions.pop(tap_id, None)
            if not session:
                return
            if client.client_id not in (session.initiator_id, session.target_id):
                return
            msg = encode_msg(MsgType.TAP_END, tap_id=tap_id)
            for cid in (session.initiator_id, session.target_id):
                peer = self._clients.get(cid)
                if peer:
                    await peer.ws.send(msg)
            return

    async def _broadcast_all_rooms(self) -> None:
        rooms = [self._room_info(r) for r in self._rooms.values()]
        msg = encode_msg(MsgType.ROOMS, rooms=rooms)
        tasks = [c.ws.send(msg) for c in self._clients.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ws_handler(self, ws: WebSocketServerProtocol) -> None:
        client_id = new_id()
        client = ClientState(ws=ws, client_id=client_id, name="Anonymous")
        joined = False
        try:
            hello_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            hello = decode_msg(hello_raw)
            if hello.get("type") != MsgType.HELLO.value:
                await ws.close(1008, "expected hello")
                return
            if self._password_digest:
                supplied = str(hello.get("password", ""))
                if not supplied:
                    await client.ws.send(
                        encode_msg(
                            MsgType.ERROR,
                            message="Password required",
                            error_code=ErrorCode.PASSWORD_REQUIRED.value,
                        )
                    )
                    await ws.close(1008, "password required")
                    return
                if not check_password(supplied, self._password_salt, self._password_digest):
                    await client.ws.send(
                        encode_msg(
                            MsgType.ERROR,
                            message="Incorrect password",
                            error_code=ErrorCode.PASSWORD_WRONG.value,
                        )
                    )
                    await ws.close(1008, "wrong password")
                    return
            name = clamp_name(str(hello.get("name", "Anonymous")))
            async with self._join_lock:
                if self._display_name_taken(name):
                    await client.ws.send(
                        encode_msg(
                            MsgType.ERROR,
                            message="Name already in use",
                            error_code=ErrorCode.NAME_TAKEN.value,
                        )
                    )
                    await ws.close(1008, "name taken")
                    return
                client.name = name
                client.is_server_operator = self._connection_is_server_operator(ws, hello)
                self._clients[client_id] = client
                joined = True
            default = self._default_room()
            client.room_id = default.room_id
            default.members.add(client_id)
            await ws.send(
                encode_msg(
                    MsgType.WELCOME,
                    client_id=client_id,
                    server_name=self.server_name,
                    ws_port=self.ws_port,
                    udp_port=self.udp_port,
                    room_id=default.room_id,
                    room_name=default.name,
                    server_operator=client.is_server_operator,
                    server_password_protected=self.password_protected,
                )
            )
            await self._send_rooms(client)
            await self._send_presence(default.room_id)

            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    data = decode_msg(raw)
                except (ValueError, TypeError):
                    continue
                await self._handle_message(client, data)
        except asyncio.TimeoutError:
            await ws.close(1008, "hello timeout")
        except websockets.ConnectionClosed:
            pass
        finally:
            if not joined:
                return
            if client.room_id:
                room = self._rooms.get(client.room_id)
                if room:
                    room.members.discard(client_id)
                    await self._send_presence(client.room_id)
            self._clients.pop(client_id, None)
            await self._broadcast_all_rooms()

    class _VoiceProtocol(asyncio.DatagramProtocol):
        def __init__(self, hub: BabbleCastHub) -> None:
            self.hub = hub

        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            packet = VoicePacket.decode(data)
            if not packet:
                return
            sender = self.hub._clients.get(packet.sender_id)
            if not sender or not sender.room_id or sender.room_id != packet.room_id:
                return
            if not self.hub._register_udp_source(sender, addr):
                return
            if sender.muted and not sender.ptt_active:
                return
            room = self.hub._rooms.get(sender.room_id)
            if not room:
                return
            transport = self.hub._udp_transport
            if not transport:
                return
            for cid in room.members:
                if cid == packet.sender_id:
                    continue
                peer = self.hub._clients.get(cid)
                if peer and peer.udp_addr:
                    transport.sendto(data, peer.udp_addr)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._default_room()
        self._ws_server = await websockets.serve(
            self._ws_handler,
            self.host,
            self.ws_port,
            ping_interval=WS_PING_INTERVAL_SEC,
            ping_timeout=WS_PING_TIMEOUT_SEC,
            max_size=2**20,
            logger=_ws_probe_logger,
        )
        transport, _ = await self._loop.create_datagram_endpoint(
            lambda: self._VoiceProtocol(self),
            local_addr=(self.host, self.udp_port),
        )
        self._udp_transport = transport
        if self.advertise:
            from babblecast.discovery_beacon import DiscoveryBeacon
            from babblecast.network import advertise_hosts_for_settings, primary_lan_ipv4

            adv_hosts = advertise_hosts_for_settings()
            if self.host not in ("0.0.0.0", "127.0.0.1") and self.host not in adv_hosts:
                adv_hosts.insert(0, self.host)
            if adv_hosts:
                self._advertiser = ServerAdvertiser(
                    self.server_name,
                    self.ws_port,
                    self.udp_port,
                    adv_hosts,
                    password_protected=self.password_protected,
                )
                self._advertiser.start()
            else:
                logger.warning(
                    "No LAN IPv4 address found — mDNS advertisement skipped"
                )
            self._beacon = DiscoveryBeacon(
                server_name=self.server_name,
                ws_port=self.ws_port,
                lan_ip=primary_lan_ipv4(),
            )
            self._beacon.start()
        logger.info("BabbleCast hub listening ws=%s udp=%s", self.ws_port, self.udp_port)

    async def stop(self) -> None:
        if self._beacon:
            self._beacon.stop()
            self._beacon = None
        if self._advertiser:
            self._advertiser.stop()
            self._advertiser = None
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
            self._ws_server = None
        if self._udp_transport:
            self._udp_transport.close()
            self._udp_transport = None
        self._clients.clear()

    async def run_forever(self) -> None:
        await self.start()
        try:
            await asyncio.Future()
        finally:
            await self.stop()


def run_server(
    host: str = "0.0.0.0",
    ws_port: int = DEFAULT_WS_PORT,
    udp_port: int = DEFAULT_UDP_PORT,
    server_name: str = "BabbleCast",
    server_password: str = "",
) -> None:
    hub = BabbleCastHub(
        host=host,
        ws_port=ws_port,
        udp_port=udp_port,
        server_name=server_name,
        server_password=server_password,
    )
    asyncio.run(hub.run_forever())
