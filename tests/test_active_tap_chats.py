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
