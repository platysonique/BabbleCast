"""Bridge-managed sessions must not open duplicate audio when speaker is not ready yet."""

from __future__ import annotations

from babblecast.client.session import ClientSession


def test_bridge_managed_without_speaker_skips_session_audio() -> None:
    session = ClientSession(link_id="link-1", bridge_managed=True, bridge_speaker=None)
    assert session.is_bridge
    session._setup_audio()
    assert session._mic is None
    assert session._speaker is None


def test_bridge_managed_can_receive_speaker_later() -> None:
    session = ClientSession(link_id="link-1", bridge_managed=True, bridge_speaker=None)
    speaker = object()
    session.set_bridge_speaker(speaker)
    assert session._bridge_speaker is speaker
