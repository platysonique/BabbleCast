"""Tests for server link info helpers."""

from __future__ import annotations

from babblecast.client.bridge import ServerLinkState
from babblecast.client.link_stats import build_link_info_rows, link_display_name


def test_link_display_name_prefers_server_name() -> None:
    link = ServerLinkState(
        link_id="abc",
        label="192.168.1.5:9513",
        host="192.168.1.5",
        port=9513,
        server_name="Crew Comms",
    )
    assert link_display_name(link) == "Crew Comms"


def test_build_link_info_rows_includes_address() -> None:
    link = ServerLinkState(
        link_id="abc123456789",
        label="Crew Comms",
        host="10.0.0.2",
        port=9513,
        server_name="Crew Comms",
        connected=True,
    )
    rows = dict(build_link_info_rows(link, None, presence_count=3, is_active=True))
    assert rows["Server name"] == "Crew Comms"
    assert rows["Address"] == "10.0.0.2:9513"
    assert rows["People in room"] == "3"
    assert rows["Active server (UI)"] == "Yes"
