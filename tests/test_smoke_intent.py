from mobile.smoke_intent import parse_smoke_connect


def test_parse_smoke_connect_valid() -> None:
    assert parse_smoke_connect("192.168.1.141:9513") == ("192.168.1.141", 9513)


def test_parse_smoke_connect_invalid() -> None:
    assert parse_smoke_connect("") is None
    assert parse_smoke_connect("nohost") is None
    assert parse_smoke_connect("192.168.1.1:99999") is None
