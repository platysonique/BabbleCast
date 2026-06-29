from babblecast.audio.android_routing import (
    AUDIO_ROUTE_BLUETOOTH,
    AUDIO_ROUTE_EARPIECE,
    AUDIO_ROUTE_SPEAKER,
    normalize_audio_route,
    resolve_playback_route,
)


def test_normalize_audio_route_defaults_unknown() -> None:
    assert normalize_audio_route(None) == AUDIO_ROUTE_SPEAKER
    assert normalize_audio_route("bogus") == AUDIO_ROUTE_SPEAKER


def test_normalize_audio_route_accepts_known() -> None:
    assert normalize_audio_route(AUDIO_ROUTE_EARPIECE) == AUDIO_ROUTE_EARPIECE
    assert normalize_audio_route(AUDIO_ROUTE_BLUETOOTH) == AUDIO_ROUTE_BLUETOOTH


def test_resolve_playback_route_auto_no_bt() -> None:
    assert resolve_playback_route("auto", bt_hfp_connected=False, auto_switch_bt=True) == AUDIO_ROUTE_SPEAKER


def test_resolve_playback_route_auto_bt_auto_switch() -> None:
    assert resolve_playback_route("auto", bt_hfp_connected=True, auto_switch_bt=True) == AUDIO_ROUTE_BLUETOOTH


def test_resolve_playback_route_auto_bt_no_auto_switch() -> None:
    assert resolve_playback_route("auto", bt_hfp_connected=True, auto_switch_bt=False) == AUDIO_ROUTE_SPEAKER


def test_resolve_playback_route_bluetooth_no_hfp() -> None:
    assert resolve_playback_route("bluetooth", bt_hfp_connected=False, auto_switch_bt=True) == AUDIO_ROUTE_SPEAKER


def test_resolve_playback_route_speaker_unchanged() -> None:
    assert resolve_playback_route("speaker", bt_hfp_connected=False, auto_switch_bt=False) == AUDIO_ROUTE_SPEAKER


def test_resolve_playback_route_earpiece_unchanged() -> None:
    assert resolve_playback_route("earpiece", bt_hfp_connected=True, auto_switch_bt=True) == AUDIO_ROUTE_EARPIECE
