"""LAN subnet scan for BabbleCast servers."""

from babblecast.network_scan import lan_subnet_scan_targets, scan_local_subnets_for_servers


def test_lan_subnet_scan_targets_includes_local_prefix() -> None:
    targets = lan_subnet_scan_targets()
    assert targets
    assert any(ip.startswith("127.") is False for ip in targets)


def test_scan_local_subnets_for_servers_mock(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.network_scan.lan_subnet_scan_targets",
        lambda: ["192.168.1.50", "192.168.1.99"],
    )
    monkeypatch.setattr(
        "babblecast.network_scan._port_open",
        lambda ip, *_a, **_k: ip == "192.168.1.50",
    )
    found = scan_local_subnets_for_servers()
    assert found == ["192.168.1.50"]
