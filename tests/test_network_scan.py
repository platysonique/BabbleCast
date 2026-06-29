"""LAN discovery via UDP beacon and mesh-aware probes."""

from unittest.mock import MagicMock

from babblecast.network_scan import LanServerHit, discover_lan_servers


def test_discover_lan_servers_from_beacon(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.discovery_beacon.request_beacons",
        lambda **_k: [("Test Studio", "192.168.1.141", 9513)],
    )
    monkeypatch.setattr("babblecast.mesh_probe.mesh_unicast_discover_targets", lambda: [])
    monkeypatch.setattr("babblecast.network.saved_lan_hosts", lambda: [])
    monkeypatch.setattr("babblecast.transport_probe.tcp_port_open", lambda *_a, **_k: True)

    found = discover_lan_servers()
    assert found == [LanServerHit(host="192.168.1.141", name="Test Studio", ws_port=9513)]


def test_discover_lan_servers_dedupes_by_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.discovery_beacon.request_beacons",
        lambda **_k: [("Test", "192.168.1.50", 9513)],
    )
    monkeypatch.setattr(
        "babblecast.mesh_probe.mesh_unicast_discover_targets",
        lambda: ["192.168.1.50"],
    )
    monkeypatch.setattr("babblecast.network.saved_lan_hosts", lambda: [])
    monkeypatch.setattr("babblecast.transport_probe.tcp_port_open", lambda *_a, **_k: True)

    found = discover_lan_servers()
    assert len(found) == 1
    assert found[0].host == "192.168.1.50"
