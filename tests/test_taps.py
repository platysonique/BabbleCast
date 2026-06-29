"""Tap note store tests."""

from __future__ import annotations

import pytest

from babblecast.taps import SavedTap, TapStore


def test_saved_tap_requires_subject() -> None:
    with pytest.raises(ValueError):
        SavedTap.create("p1", "Alice", "LAN", "   ")


def test_tap_store_migrates_legacy_reminder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.taps.app_config_dir",
        lambda *, create=False: tmp_path,
    )
    path = tmp_path / "taps.json"
    path.write_text(
        '{"taps": [{"save_id": "a", "peer_id": "p", "peer_name": "Bob", '
        '"server_label": "S", "reminder": "Old subject", "detail": "", "done": false}]}',
        encoding="utf-8",
    )
    store = TapStore()
    tap = store.get("a")
    assert tap is not None
    assert tap.display_subject == "Old subject"


def test_tap_store_update_subject_and_detail(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.taps.app_config_dir",
        lambda *, create=False: tmp_path,
    )
    store = TapStore()
    store.add(
        SavedTap.create("p1", "Alice", "LAN", "Follow up", detail="Initial")
    )
    save_id = store.items[0].save_id
    assert store.update(save_id, subject="Updated", detail="More info")
    reloaded = TapStore().get(save_id)
    assert reloaded is not None
    assert reloaded.subject == "Updated"
    assert reloaded.detail == "More info"
