from __future__ import annotations

from unittest.mock import MagicMock, patch

from babblecast.client.bridge import BridgeManager


def test_set_audio_route_pre_audio_saves_sync() -> None:
    bridge = BridgeManager()
    bridge._audio_started = False
    with patch("babblecast.client.bridge.save_settings") as save, patch(
        "babblecast.client.bridge.platform_name", return_value="android"
    ), patch("babblecast.audio.android_route_worker.get_route_worker") as gw:
        bridge.set_audio_route("earpiece")
        save.assert_called_once()
        gw.assert_not_called()


def test_set_audio_route_enqueues_worker_when_audio_started() -> None:
    bridge = BridgeManager()
    bridge._audio_started = True
    bridge._speaker = MagicMock()
    worker = MagicMock()
    with patch("babblecast.client.bridge.save_settings") as save, patch(
        "babblecast.client.bridge.platform_name", return_value="android"
    ), patch("babblecast.audio.android_route_worker.get_route_worker", return_value=worker):
        bridge.set_audio_route("speaker", source="ui")
        save.assert_not_called()
        worker.request_route.assert_called_once()
        bridge._speaker.set_route.assert_called_once_with("speaker")


def test_on_route_worker_complete_defers_main_thread() -> None:
    bridge = BridgeManager()
    with patch("babblecast.client.bridge._defer_main_thread") as defer, patch(
        "babblecast.client.bridge.save_settings"
    ):
        bridge._on_route_worker_complete("speaker", True)
        defer.assert_called_once()
