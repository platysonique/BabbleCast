"""Integration test for BabbleCast hub WebSocket flow."""

from __future__ import annotations

import asyncio

import pytest
import websockets

from babblecast.protocol import MsgType, decode_msg, encode_msg
from babblecast.server.hub import BabbleCastHub, ClientState


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
            assert err.get("error_code") == "last_room"
            assert "last room" in err.get("message", "").lower()
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_duplicate_display_name_rejected() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18773, udp_port=18774, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18773") as ws_a:
            await ws_a.send(encode_msg(MsgType.HELLO, name="Director"))
            welcome = decode_msg(await asyncio.wait_for(ws_a.recv(), timeout=2))
            assert welcome["type"] == MsgType.WELCOME.value

            async with websockets.connect("ws://127.0.0.1:18773") as ws_b:
                await ws_b.send(encode_msg(MsgType.HELLO, name="director"))
                err = None
                for _ in range(8):
                    msg = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
                    if msg.get("type") == MsgType.ERROR.value:
                        err = msg
                        break
                assert err is not None
                assert err.get("error_code") == "name_taken"
                assert "name already in use" in err.get("message", "").lower()
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_display_name_released_after_disconnect() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18775, udp_port=18776, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18775") as ws_a:
            await ws_a.send(encode_msg(MsgType.HELLO, name="Gaffer"))
            decode_msg(await asyncio.wait_for(ws_a.recv(), timeout=2))

        async with websockets.connect("ws://127.0.0.1:18775") as ws_b:
            await ws_b.send(encode_msg(MsgType.HELLO, name="Gaffer"))
            welcome = decode_msg(await asyncio.wait_for(ws_b.recv(), timeout=2))
            assert welcome["type"] == MsgType.WELCOME.value
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_password_protected_server() -> None:
    hub = BabbleCastHub(
        host="127.0.0.1",
        ws_port=18777,
        udp_port=18778,
        advertise=False,
        server_password="secret",
    )
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18777") as ws:
            await ws.send(encode_msg(MsgType.HELLO, name="Guest"))
            err = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
            assert err["type"] == MsgType.ERROR.value
            assert err.get("error_code") == "password_required"

        async with websockets.connect("ws://127.0.0.1:18777") as ws:
            await ws.send(encode_msg(MsgType.HELLO, name="Guest", password="nope"))
            err = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
            assert err.get("error_code") == "password_wrong"

        async with websockets.connect("ws://127.0.0.1:18777") as ws:
            await ws.send(encode_msg(MsgType.HELLO, name="Guest", password="secret"))
            welcome = decode_msg(await asyncio.wait_for(ws.recv(), timeout=2))
            assert welcome["type"] == MsgType.WELCOME.value
    finally:
        await hub.stop()


def test_udp_source_must_match_registered_addr() -> None:
    hub = BabbleCastHub(advertise=False)
    client = ClientState(ws=None, client_id="c1", name="A")  # type: ignore[arg-type]
    client.udp_addr = ("127.0.0.1", 5000)
    assert hub._register_udp_source(client, ("127.0.0.1", 5000))
    assert client.udp_source == ("127.0.0.1", 5000)
    assert hub._register_udp_source(client, ("127.0.0.1", 5000))
    assert not hub._register_udp_source(client, ("127.0.0.1", 5001))
    assert not hub._register_udp_source(client, ("192.168.1.5", 5000))
    client.udp_addr = ("10.0.0.2", 6000)
    assert client.udp_addr == ("10.0.0.2", 6000)
    fresh = ClientState(ws=None, client_id="c2", name="B")  # type: ignore[arg-type]
    fresh.udp_addr = ("127.0.0.1", 7000)
    assert not hub._register_udp_source(fresh, ("127.0.0.1", 7001))
    assert hub._register_udp_source(fresh, ("192.168.1.9", 7000))


@pytest.mark.asyncio
async def test_protected_room_requires_password_to_join() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18779, udp_port=18780, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18779") as ws_host:
            await ws_host.send(encode_msg(MsgType.HELLO, name="Boss"))
            welcome = decode_msg(await asyncio.wait_for(ws_host.recv(), timeout=2))
            host_id = welcome["client_id"]

            await ws_host.send(encode_msg(MsgType.CREATE_ROOM, name="Private", password="secret"))
            private_room = None
            for _ in range(12):
                msg = decode_msg(await asyncio.wait_for(ws_host.recv(), timeout=2))
                if msg.get("type") == MsgType.ROOM_CREATED.value:
                    private_room = msg["room"]["room_id"]
                    assert msg["room"]["password_protected"] is True
                    assert msg["room"]["creator_id"] == host_id
                    break
            assert private_room

            async with websockets.connect("ws://127.0.0.1:18779") as ws_guest:
                await ws_guest.send(encode_msg(MsgType.HELLO, name="Guest"))
                decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))

                await ws_guest.send(encode_msg(MsgType.JOIN_ROOM, room_id=private_room))
                err = None
                for _ in range(12):
                    msg = decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))
                    if msg.get("type") == MsgType.ERROR.value:
                        err = msg
                        break
                assert err is not None
                assert err.get("error_code") == "room_password_required"

                await ws_guest.send(
                    encode_msg(MsgType.JOIN_ROOM, room_id=private_room, password="nope")
                )
                err = None
                for _ in range(12):
                    msg = decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))
                    if msg.get("type") == MsgType.ERROR.value:
                        err = msg
                        break
                assert err is not None
                assert err.get("error_code") == "room_password_wrong"

                await ws_guest.send(
                    encode_msg(MsgType.JOIN_ROOM, room_id=private_room, password="secret")
                )
                joined = decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))
                assert joined.get("type") == MsgType.JOINED.value
                assert joined["room_id"] == private_room
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_server_operator_bypasses_room_password() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18783, udp_port=18784, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18783") as ws_guest:
            await ws_guest.send(encode_msg(MsgType.HELLO, name="Guest"))
            decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))

            await ws_guest.send(encode_msg(MsgType.CREATE_ROOM, name="Staff Only", password="secret"))
            private_room = None
            for _ in range(12):
                msg = decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))
                if msg.get("type") == MsgType.ROOM_CREATED.value:
                    private_room = msg["room"]["room_id"]
                    break
            assert private_room

        async with websockets.connect("ws://127.0.0.1:18783") as ws_host:
            await ws_host.send(encode_msg(MsgType.HELLO, name="Host", server_operator=True))
            welcome = decode_msg(await asyncio.wait_for(ws_host.recv(), timeout=2))
            assert welcome.get("server_operator") is True

            await ws_host.send(encode_msg(MsgType.JOIN_ROOM, room_id=private_room))
            joined = None
            for _ in range(12):
                msg = decode_msg(await asyncio.wait_for(ws_host.recv(), timeout=2))
                if msg.get("type") == MsgType.JOINED.value:
                    joined = msg
                    break
            assert joined is not None
            assert joined["room_id"] == private_room
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_only_room_creator_can_delete() -> None:
    hub = BabbleCastHub(host="127.0.0.1", ws_port=18781, udp_port=18782, advertise=False)
    await hub.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18781") as ws_host:
            await ws_host.send(encode_msg(MsgType.HELLO, name="Boss"))
            decode_msg(await asyncio.wait_for(ws_host.recv(), timeout=2))

            await ws_host.send(encode_msg(MsgType.CREATE_ROOM, name="Ops"))
            ops_room = None
            for _ in range(12):
                msg = decode_msg(await asyncio.wait_for(ws_host.recv(), timeout=2))
                if msg.get("type") == MsgType.ROOM_CREATED.value:
                    ops_room = msg["room"]["room_id"]
                    break
            assert ops_room

            async with websockets.connect("ws://127.0.0.1:18781") as ws_guest:
                await ws_guest.send(encode_msg(MsgType.HELLO, name="Guest"))
                decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))

                await ws_guest.send(encode_msg(MsgType.DELETE_ROOM, room_id=ops_room))
                err = None
                for _ in range(12):
                    msg = decode_msg(await asyncio.wait_for(ws_guest.recv(), timeout=2))
                    if msg.get("type") == MsgType.ERROR.value:
                        err = msg
                        break
                assert err is not None
                assert err.get("error_code") == "not_room_owner"
    finally:
        await hub.stop()
