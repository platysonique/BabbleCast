"""Subnet-aware address selection and LAN scan."""

from babblecast.network import pick_reachable_server_ip, same_subnet_24


def test_same_subnet_24() -> None:
    assert same_subnet_24("192.168.1.10", "192.168.1.99")
    assert not same_subnet_24("192.168.0.10", "192.168.1.99")


def test_pick_reachable_server_ip_prefers_matching_subnet() -> None:
    server_ips = ["192.168.0.50", "192.168.1.20"]
    client_ips = ["192.168.1.105"]
    assert pick_reachable_server_ip(server_ips, client_ips=client_ips) == "192.168.1.20"


def test_pick_reachable_server_ip_skips_loopback() -> None:
    assert pick_reachable_server_ip(["127.0.0.1", "10.0.0.5"], client_ips=["10.0.0.2"]) == "10.0.0.5"
