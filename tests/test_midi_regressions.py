"""Regression tests for MIDI wiring in Qt client."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_context_menus_imported() -> None:
    drawer = _read("babblecast/client/qt/detail_drawer.py")
    main = _read("babblecast/client/qt/main_window.py")
    link = _read("babblecast/client/qt/server_link_widget.py")
    assert "context_menus" in drawer
    assert "context_menus" in main
    assert "context_menus" in link


def test_main_window_midi_menu() -> None:
    main = _read("babblecast/client/qt/main_window.py")
    assert 'addMenu("MIDI")' in main
    assert "Mappings" in main
    assert "MidiMapperService" in main


def test_shutdown_stops_midi_before_bridge() -> None:
    main = _read("babblecast/client/qt/main_window.py")
    tree = ast.parse(main)
    func = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_shutdown_and_quit"
    )
    src = ast.get_source_segment(main, func) or ""
    assert "midi.shutdown" in src
    assert src.index("midi.shutdown") < src.index("bridge.shutdown")


def test_config_has_midi_maps() -> None:
    cfg = _read("babblecast/config.py")
    assert "midi_maps" in cfg
