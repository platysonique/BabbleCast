"""Connect target and advertisement helpers."""

from babblecast.network import (
    advertise_hosts_for_settings,
    is_private_lan_ipv4,
    is_valid_connect_target,
)


def test_is_private_lan_ipv4() -> None:
    assert is_private_lan_ipv4("192.168.1.10")
    assert is_private_lan_ipv4("10.0.0.5")
    assert not is_private_lan_ipv4("8.8.8.8")


def test_is_valid_connect_target() -> None:
    assert is_valid_connect_target("192.168.1.10")
    assert is_valid_connect_target("11.2.9.10")
    assert is_valid_connect_target("studio.babblecast.local")
    assert is_valid_connect_target("127.0.0.1")
    assert not is_valid_connect_target("8.8.8.8")


def test_advertise_hosts_uses_lan_ips(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.network.local_ipv4_addresses",
        lambda **_: ["192.168.1.42"],
    )
    assert advertise_hosts_for_settings() == ["192.168.1.42"]
