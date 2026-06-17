"""Bridge manager unit tests."""

from __future__ import annotations

from babblecast.client.bridge import BridgeManager
from babblecast.constants import composite_participant_key


def test_composite_participant_key() -> None:
    assert composite_participant_key("link1", "user42") == "link1:user42"


def test_bridge_link_state() -> None:
    mgr = BridgeManager()
    assert mgr.links == []
    mgr.set_listen_muted("missing", True)
    mgr.set_mic_muted("missing", True)
    mgr.disconnect("missing")
