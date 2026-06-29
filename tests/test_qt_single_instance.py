"""Tests for Qt single-instance guard."""

from __future__ import annotations

from pathlib import Path


def test_single_instance_module_present() -> None:
    source = (
        Path(__file__).resolve().parent.parent
        / "babblecast"
        / "client"
        / "qt"
        / "single_instance.py"
    ).read_text(encoding="utf-8")
    assert "QLocalServer" in source
    assert "another_instance_running" in source


def test_bbc_wrapper_does_not_exec_a_python() -> None:
    source = (
        Path(__file__).resolve().parent.parent / "packaging" / "linux" / "bbc-wrapper.sh"
    ).read_text(encoding="utf-8")
    assert 'exec -a BabbleCast "${PY}"' not in source
    assert 'exec "${BBC}" client' in source
