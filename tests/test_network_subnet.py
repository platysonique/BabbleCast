"""BabbleCast subnet (11.2.9.x) helpers."""

from babblecast.constants import babblecast_subnet_example_host, babblecast_subnet_prefix
from babblecast.network import babblecast_scan_targets, is_babblecast_subnet_ip, pick_reachable_server_ip


def test_babblecast_subnet_prefix() -> None:
    assert babblecast_subnet_prefix() == "11.2.9"
    assert babblecast_subnet_example_host(10) == "11.2.9.10"


def test_is_babblecast_subnet_ip() -> None:
    assert is_babblecast_subnet_ip("11.2.9.10")
    assert not is_babblecast_subnet_ip("192.168.1.10")
    assert not is_babblecast_subnet_ip("127.0.0.1")


def test_babblecast_scan_targets_only_project_subnet() -> None:
    targets = babblecast_scan_targets()
    assert len(targets) == 254
    assert targets[0] == "11.2.9.1"
    assert targets[-1] == "11.2.9.254"
    assert all(is_babblecast_subnet_ip(t) for t in targets)


def test_pick_reachable_prefers_matching_subnet() -> None:
    server_ips = ["192.168.0.50", "11.2.9.20"]
    client_ips = ["11.2.9.105"]
    assert pick_reachable_server_ip(server_ips, client_ips=client_ips) == "11.2.9.20"
