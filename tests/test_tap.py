"""Hub Tap session routing tests."""

from __future__ import annotations

import asyncio

import pytest
import websockets

from babblecast.protocol import MsgType, decode_msg, encode_msg
from babblecast.server.hub import BabbleCastHub


@pytest.mark.asyncio
async def test_tap_private_chat() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18767, udp_port=18768, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18767") as ws_a, websockets.connect(
            "ws://127.0.0.1:18767"
        ) as ws_b:
            await ws_a.send(encode_msg(MsgType.HELLO, name="Alice"))
            welcome_a = decode_msg(await asyncio.wait_for(ws_a.recv(), timeout=2))
            id_a = welcome_a["client_id"]

            await ws_b.send(encode_msg(MsgType.HELLO, name="Bob"))
            welcome_b = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
            id_b = welcome_b["client_id"]

            await ws_a.send(encode_msg(MsgType.TAP, target_id=id_b, text="ping"))
            tap_id = None
            for _ in range(10):
                msg = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
                if msg.get("type") == MsgType.TAP_RECEIVED.value:
                    tap_id = msg["tap_id"]
                    assert msg["from_name"] == "Alice"
                    break
            assert tap_id

            await ws_a.send(encode_msg(MsgType.TAP_OPEN, tap_id=tap_id))
            for _ in range(5):
                msg = decode_msg(await asyncio.wait_for(ws_a.recv(), timeout=2))
                if msg.get("type") == MsgType.TAP_OPEN.value:
                    break

            await ws_a.send(encode_msg(MsgType.TAP_CHAT, tap_id=tap_id, text="secret"))
            chat = None
            for _ in range(10):
                msg = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
                if msg.get("type") == MsgType.TAP_CHAT.value:
                    chat = msg
                    break
            assert chat is not None
            assert chat["text"] == "secret"
            assert chat["name"] == "Alice"

            await ws_a.send(encode_msg(MsgType.TAP_END, tap_id=tap_id))
            ended = None
            for _ in range(10):
                msg = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
                if msg.get("type") == MsgType.TAP_END.value:
                    ended = msg
                    break
            assert ended is not None
    finally:
        await hub.stop()
