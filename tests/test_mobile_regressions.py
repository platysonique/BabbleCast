"""Regression guards for mobile UI — catches __init__ scoping bugs before device smoke."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ROOT / "mobile" / "screens.py"


def _module_import_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _class_method_load_names(path: Path, class_name: str) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name == "__init__":
                continue
            loaded: set[str] = set()
            for sub in ast.walk(item):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                    loaded.add(sub.id)
            out[item.name] = loaded
    return out


MODULE_IMPORTS = _module_import_names(SCREENS)

# Names used across LiveScreen / SettingsScreen methods that must not rely on __init__ locals.
_CONNECT_PATH_SYMBOLS = frozenset({"is_android", "MDFlatButton", "MDRaisedButton"})


@pytest.mark.parametrize("class_name", ["LiveScreen", "SettingsScreen"])
def test_connect_path_symbols_imported_at_module_level(class_name: str) -> None:
    methods = _class_method_load_names(SCREENS, class_name)
    offenders: list[str] = []
    for method, names in methods.items():
        for sym in _CONNECT_PATH_SYMBOLS & names:
            if sym not in MODULE_IMPORTS:
                offenders.append(f"{class_name}.{method} uses {sym} without module import")
    assert not offenders, "\n".join(offenders)


def test_screens_source_has_module_level_connect_imports() -> None:
    text = SCREENS.read_text(encoding="utf-8")
    assert "from mobile.platform_ui import is_android" in text
    assert "from kivymd.uix.button import MDFlatButton, MDRaisedButton" in text


def test_branding_asset_file_exists() -> None:
    assert (ROOT / "assets" / "splash.png").is_file()


def test_live_screen_android_admin_helpers_defined() -> None:
    source = SCREENS.read_text(encoding="utf-8")
    assert "def set_room_password_display" in source
    assert "self._room_pwd_label" in source
    assert "def set_self_mic_level" not in source.split("class LiveScreen")[1].split("class SettingsScreen")[0]


def test_settings_screen_has_mic_meter() -> None:
    source = SCREENS.read_text(encoding="utf-8")
    settings_block = source.split("class SettingsScreen", 1)[1]
    assert "def set_self_mic_level" in settings_block
    assert "self._self_meter" in settings_block
    assert "VerticalMeter" in settings_block


def test_controller_refresh_admin_room_password_targets_live() -> None:
    text = (ROOT / "mobile" / "controller.py").read_text(encoding="utf-8")
    assert "set_room_password_display" in text
    assert "set_self_mic_level" in text
    assert "ensure_self_audio_meter" in text


def test_live_on_enter_uses_module_level_is_android() -> None:
    """LiveScreen.on_enter runs on every connect tab switch — must not NameError."""
    source = SCREENS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "LiveScreen":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "on_enter":
                    names = {
                        sub.id
                        for sub in ast.walk(item)
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
                    }
                    if "is_android" in names:
                        assert "is_android" in MODULE_IMPORTS
                    return
    pytest.fail("LiveScreen.on_enter not found")
