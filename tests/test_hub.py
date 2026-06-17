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
            for _ in range(10):
                msg = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
                if msg.get("type") == MsgType.ROOM_CREATED.value:
                    created = msg
                    break
            assert created is not None
            new_room = created["room"]["room_id"]

            await ws.send(encode_msg(MsgType.JOIN_ROOM, room_id=new_room))
            joined = None
            for _ in range(10):
                msg = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
                if msg.get("type") == MsgType.JOINED.value:
                    joined = msg
                    break
            assert joined is not None
            assert joined["room_id"] == new_room
    finally:
        await hub.stop()
