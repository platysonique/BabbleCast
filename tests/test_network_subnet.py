"""BabbleCast virtual addressing (11.2.x.x)."""

from babblecast.address import (
    BABBLECAST_AUTO_DOMAIN,
    allocate_babblecast_ip,
    babblecast_auto_subnet,
    babblecast_prefix,
    format_babblecast_ip,
    is_babblecast_ip,
    parse_address_suffix,
    validate_address_suffix,
)


def test_babblecast_prefix() -> None:
    assert babblecast_prefix() == "11.2"
    assert babblecast_auto_subnet() == "11.2.9.x"
    assert BABBLECAST_AUTO_DOMAIN == 9


def test_is_babblecast_ip() -> None:
    assert is_babblecast_ip("11.2.9.10")
    assert is_babblecast_ip("11.2.142.1")
    assert not is_babblecast_ip("192.168.1.10")
    assert not is_babblecast_ip("11.2.9.0")
    assert not is_babblecast_ip("127.0.0.1")


def test_parse_address_suffix() -> None:
    assert parse_address_suffix("9") == (9, None)
    assert parse_address_suffix("9.10") == (9, 10)
    assert parse_address_suffix("142.88") == (142, 88)


def test_validate_address_suffix_rejects_invalid() -> None:
    assert validate_address_suffix("9.0") is not None
    assert validate_address_suffix("300.1") is not None


def test_allocate_custom_full_host(monkeypatch) -> None:
    monkeypatch.setattr("babblecast.address._port_open", lambda *_a, **_k: False)
    ip = allocate_babblecast_ip(custom=True, suffix="42.15")
    assert ip == "11.2.42.15"


def test_allocate_auto_always_uses_nine_subnet(monkeypatch) -> None:
    monkeypatch.setattr("babblecast.address._port_open", lambda *_a, **_k: False)
    ip = allocate_babblecast_ip(custom=False)
    assert ip.startswith("11.2.9.")
    assert is_babblecast_ip(ip)
