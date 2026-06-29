"""Active tap chat persistence tests."""

from __future__ import annotations

from babblecast.active_tap_chats import ActiveTapChatStore


def test_active_tap_chat_store_persists_messages(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.active_tap_chats.app_config_dir",
        lambda *, create=False: tmp_path,
    )
    store = ActiveTapChatStore()
    store.record_received(
        tap_id="tap-1",
        link_host="127.0.0.1",
        link_port=9513,
        peer_id="peer-a",
        peer_name="Alice",
        server_label="LAN",
    )
    store.append_message("tap-1", name="Bob", text="hello", ts="12:00")

    reloaded = ActiveTapChatStore()
    chat = reloaded.get("tap-1")
    assert chat is not None
    assert chat.peer_name == "Alice"
    assert len(chat.messages) == 1
    assert chat.messages[0]["text"] == "hello"

    reloaded.remove("tap-1")
    assert ActiveTapChatStore().get("tap-1") is None


def test_active_tap_chat_restore_remaps_peer_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.active_tap_chats.app_config_dir",
        lambda *, create=False: tmp_path,
    )
    store = ActiveTapChatStore()
    store.record_received(
        tap_id="tap-2",
        link_host="10.0.0.5",
        link_port=9513,
        peer_id="old-id",
        peer_name="Cam",
        server_label="Studio",
    )
    mapping = store.tap_ids_for_server(
        "link-1",
        host="10.0.0.5",
        port=9513,
        participants=[{"client_id": "new-id", "name": "Cam"}],
    )
    assert mapping[("link-1", "new-id")] == "tap-2"
    assert store.get("tap-2").peer_id == "new-id"


def test_active_tap_chat_clear_messages_keeps_thread(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.active_tap_chats.app_config_dir",
        lambda *, create=False: tmp_path,
    )
    store = ActiveTapChatStore()
    store.record_received(
        tap_id="tap-3",
        link_host="127.0.0.1",
        link_port=9513,
        peer_id="p1",
        peer_name="Pat",
        server_label="LAN",
    )
    store.append_message("tap-3", name="Pat", text="ping", ts="09:00")
    store.clear_messages("tap-3")
    chat = store.get("tap-3")
    assert chat is not None
    assert chat.messages == []
    assert chat.peer_name == "Pat"


def test_record_received_rebinds_tap_id_for_same_peer(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.active_tap_chats.app_config_dir",
        lambda *, create=False: tmp_path,
    )
    store = ActiveTapChatStore()
    store.record_received(
        tap_id="tap-old",
        link_host="127.0.0.1",
        link_port=9513,
        peer_id="peer-a",
        peer_name="Alice",
        server_label="LAN",
    )
    store.append_message("tap-old", name="Alice", text="first", ts="10:00")

    chat = store.record_received(
        tap_id="tap-new",
        link_host="127.0.0.1",
        link_port=9513,
        peer_id="peer-a",
        peer_name="Alice",
        server_label="LAN",
    )
    assert chat.tap_id == "tap-new"
    assert store.get("tap-old") is None
    assert len(store.get("tap-new").messages) == 1
    assert store.get("tap-new").messages[0]["text"] == "first"


def test_tap_ids_for_server_picks_most_recent_per_peer(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.active_tap_chats.app_config_dir",
        lambda *, create=False: tmp_path,
    )
    store = ActiveTapChatStore()
    store.record_received(
        tap_id="tap-a",
        link_host="127.0.0.1",
        link_port=9513,
        peer_id="peer-a",
        peer_name="Alice",
        server_label="LAN",
    )
    store.record_received(
        tap_id="tap-b",
        link_host="127.0.0.1",
        link_port=9513,
        peer_id="peer-a",
        peer_name="Alice",
        server_label="LAN",
    )
    mapping = store.tap_ids_for_server(
        "link-1",
        host="127.0.0.1",
        port=9513,
        participants=[{"client_id": "peer-a", "name": "Alice"}],
    )
    assert mapping[("link-1", "peer-a")] == "tap-b"
    assert store.get("tap-a") is None
