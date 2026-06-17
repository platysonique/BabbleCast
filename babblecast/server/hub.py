"""Async BabbleCast hub — rooms, chat, presence, voice relay."""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from babblecast.constants import DEFAULT_UDP_PORT, DEFAULT_WS_PORT
from babblecast.discovery import ServerAdvertiser
from babblecast.protocol import (
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
    udp_addr: tuple[str, int] | None = None

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
    ) -> None:
        self.host = host
        self.ws_port = ws_port
        self.udp_port = udp_port
        self.server_name = server_name
        self.advertise = advertise
        self._clients: dict[str, ClientState] = {}
        self._rooms: dict[str, Room] = {}
        self._tap_sessions: dict[str, TapSession] = {}
        self._ws_server = None
        self._udp_transport = None
        self._advertiser: ServerAdvertiser | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _default_room(self) -> Room:
        for room in self._rooms.values():
            return room
        room = Room(room_id=new_id(), name="General")
        self._rooms[room.room_id] = room
        return room

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

    async def _send_rooms(self, client: ClientState) -> None:
        rooms = [
            RoomInfo(r.room_id, r.name, len(r.members)).to_dict()
            for r in self._rooms.values()
        ]
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
            room = Room(room_id=new_id(), name=name)
            self._rooms[room.room_id] = room
            if client.room_id:
                old = self._rooms.get(client.room_id)
                if old:
                    old.members.discard(client.client_id)
                    await self._send_presence(client.room_id)
            client.room_id = room.room_id
            room.members.add(client.client_id)
            await client.ws.send(
                encode_msg(MsgType.ROOM_CREATED, room=RoomInfo(room.room_id, room.name, 1).to_dict())
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
                await client.ws.send(encode_msg(MsgType.ERROR, message="Room not found"))
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
                await client.ws.send(encode_msg(MsgType.ERROR, message="Room not found"))
                return
            if len(self._rooms) <= 1:
                await client.ws.send(encode_msg(MsgType.ERROR, message="Cannot delete the last room"))
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
            client.voice_level = float(data.get("level", 0.0))
            client.speaking = client.voice_level > 0.08 and not client.muted
            if client.room_id:
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
                await client.ws.send(encode_msg(MsgType.ERROR, message="User not found"))
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
                await client.ws.send(encode_msg(MsgType.ERROR, message="Tap not found"))
                return
            if client.client_id not in (session.initiator_id, session.target_id):
                await client.ws.send(encode_msg(MsgType.ERROR, message="Not a tap participant"))
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
                await client.ws.send(encode_msg(MsgType.ERROR, message="Tap not open"))
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
        rooms = [
            RoomInfo(r.room_id, r.name, len(r.members)).to_dict()
            for r in self._rooms.values()
        ]
        msg = encode_msg(MsgType.ROOMS, rooms=rooms)
        tasks = [c.ws.send(msg) for c in self._clients.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ws_handler(self, ws: WebSocketServerProtocol) -> None:
        client_id = new_id()
        client = ClientState(ws=ws, client_id=client_id, name="Anonymous")
        self._clients[client_id] = client
        try:
            hello_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            hello = decode_msg(hello_raw)
            if hello.get("type") != MsgType.HELLO.value:
                await ws.close(1008, "expected hello")
                return
            client.name = clamp_name(str(hello.get("name", "Anonymous")))
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
            registered = sender.udp_addr
            if registered is None:
                sender.udp_addr = addr
            elif registered[1] != addr[1]:
                # Port must match the client's bound UDP socket (anti-spoof).
                return
            # IP in udp_endpoint may differ from datagram source (loopback vs LAN).
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
            ping_interval=20,
            ping_timeout=20,
            max_size=2**20,
        )
        transport, _ = await self._loop.create_datagram_endpoint(
            lambda: self._VoiceProtocol(self),
            local_addr=(self.host, self.udp_port),
        )
        self._udp_transport = transport
        if self.advertise:
            adv_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    adv_host = s.getsockname()[0]
            except OSError:
                pass
            self._advertiser = ServerAdvertiser(self.server_name, self.ws_port, self.udp_port, adv_host)
            self._advertiser.start()
        logger.info("BabbleCast hub listening ws=%s udp=%s", self.ws_port, self.udp_port)

    async def stop(self) -> None:
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
) -> None:
    hub = BabbleCastHub(host=host, ws_port=ws_port, udp_port=udp_port, server_name=server_name)
    asyncio.run(hub.run_forever())
