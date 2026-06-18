from babblecast.audio.android_routing import (
    AUDIO_ROUTE_BLUETOOTH,
    AUDIO_ROUTE_EARPIECE,
    AUDIO_ROUTE_SPEAKER,
    normalize_audio_route,
)


def test_normalize_audio_route_defaults_unknown() -> None:
    assert normalize_audio_route(None) == AUDIO_ROUTE_SPEAKER
    assert normalize_audio_route("bogus") == AUDIO_ROUTE_SPEAKER


def test_normalize_audio_route_accepts_known() -> None:
    assert normalize_audio_route(AUDIO_ROUTE_EARPIECE) == AUDIO_ROUTE_EARPIECE
    assert normalize_audio_route(AUDIO_ROUTE_BLUETOOTH) == AUDIO_ROUTE_BLUETOOTH
