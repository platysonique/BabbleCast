"""Integration test for BabbleCast hub WebSocket flow."""

from __future__ import annotations

import asyncio

import pytest
import websockets

from babblecast.protocol import MsgType, decode_msg, encode_msg
from babblecast.server.hub import BabbleCastHub


@pytest.mark.asyncio
async def test_hub_hello_and_chat() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18765, udp_port=18766, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18765") as ws:
            await ws.send(encode_msg(MsgType.HELLO, name="Tester"))
            welcome = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
            assert welcome["type"] == MsgType.WELCOME.value
            client_id = welcome["client_id"]
            room_id = welcome["room_id"]

            await ws.send(encode_msg(MsgType.CHAT, text="hi room"))
            chat = None
            for _ in range(10):
                msg = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
                if msg.get("type") == MsgType.CHAT.value:
                    chat = msg
                    break
            assert chat is not None
            assert chat["text"] == "hi room"
            assert chat["client_id"] == client_id

            await ws.send(encode_msg(MsgType.CREATE_ROOM, name="Ops"))
            created = None
            joined = None
            for _ in range(15):
                msg = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
                if msg.get("type") == MsgType.ROOM_CREATED.value:
                    created = msg
                if msg.get("type") == MsgType.JOINED.value:
                    joined = msg
                if created and joined:
                    break
            assert created is not None
            new_room = created["room"]["room_id"]
            assert joined is not None
            assert joined["room_id"] == new_room
            assert joined.get("room_name") == "Ops"
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_created_rooms_visible_to_all_clients_on_same_hub() -> None:
    """Rooms live on one server process; every connected client gets ROOMS broadcasts."""
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18767, udp_port=18768, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18767") as ws_a:
            await ws_a.send(encode_msg(MsgType.HELLO, name="Host"))
            decode_msg(await ws_a.recv())  # welcome

            async with websockets.connect("ws://127.0.0.1:18767") as ws_b:
                await ws_b.send(encode_msg(MsgType.HELLO, name="Guest"))
                decode_msg(await ws_b.recv())  # welcome

                await ws_a.send(encode_msg(MsgType.CREATE_ROOM, name="Ops"))
                rooms_for_b: list[dict] | None = None
                for _ in range(12):
                    msg = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
                    if msg.get("type") == MsgType.ROOMS.value:
                        names = [r.get("name") for r in msg.get("rooms", [])]
                        if "Ops" in names:
                            rooms_for_b = msg.get("rooms", [])
                            break
                assert rooms_for_b is not None
                assert any(r.get("name") == "Ops" for r in rooms_for_b)
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_delete_room_moves_members_and_broadcasts() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18769, udp_port=18770, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18769") as ws_a:
            await ws_a.send(encode_msg(MsgType.HELLO, name="Alice"))
            welcome_a = decode_msg(await asyncio.wait_for(ws_a.recv(), timeout=2))
            default_room = welcome_a["room_id"]

            async with websockets.connect("ws://127.0.0.1:18769") as ws_b:
                await ws_b.send(encode_msg(MsgType.HELLO, name="Bob"))
                decode_msg(await ws_b.recv())

                await ws_a.send(encode_msg(MsgType.CREATE_ROOM, name="Ops"))
                ops_room = None
                for _ in range(12):
                    msg = decode_msg(await asyncio.wait_for(ws_a.recv(), timeout=2))
                    if msg.get("type") == MsgType.ROOM_CREATED.value:
                        ops_room = msg["room"]["room_id"]
                        break
                assert ops_room

                await ws_b.send(encode_msg(MsgType.JOIN_ROOM, room_id=ops_room))
                joined_b = None
                for _ in range(12):
                    msg = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
                    if msg.get("type") == MsgType.JOINED.value:
                        joined_b = msg
                        break
                assert joined_b is not None
                assert joined_b["room_id"] == ops_room

                await ws_a.send(encode_msg(MsgType.DELETE_ROOM, room_id=ops_room))
                moved = None
                deleted = None
                for _ in range(15):
                    msg = decode_msg(await asyncio.wait_for(ws_a.recv(), timeout=2))
                    if msg.get("type") == MsgType.JOINED.value:
                        moved = msg
                    if msg.get("type") == MsgType.ROOM_DELETED.value:
                        deleted = msg
                    if moved and deleted:
                        break
                assert moved is not None
                assert moved["room_id"] == default_room
                assert deleted is not None
                assert deleted["room_id"] == ops_room

                deleted_b = None
                for _ in range(10):
                    msg = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
                    if msg.get("type") == MsgType.ROOM_DELETED.value:
                        deleted_b = msg
                        break
                assert deleted_b is not None
                assert deleted_b["room_id"] == ops_room
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_cannot_delete_last_room() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18771, udp_port=18772, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18771") as ws:
            await ws.send(encode_msg(MsgType.HELLO, name="Solo"))
            welcome = decode_msg(await ws.recv())
            only_room = welcome["room_id"]
            await ws.send(encode_msg(MsgType.DELETE_ROOM, room_id=only_room))
            err = None
            for _ in range(10):
                msg = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
                if msg.get("type") == MsgType.ERROR.value:
                    err = msg
                    break
            assert err is not None
            assert "last room" in err.get("message", "").lower()
    finally:
        await hub.stop()
