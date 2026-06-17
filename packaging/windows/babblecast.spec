# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows BabbleCast installer build."""

import sys
from pathlib import Path

root = Path(SPECPATH).parent.parent

a = Analysis(
    [str(root / "babblecast" / "cli.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "babblecast",
        "babblecast.client.qt.main_window",
        "babblecast.server.embedded",
        "babblecast.server.hub",
        "opuslib",
        "noisereduce",
        "scipy",
        "sounddevice",
        "zeroconf",
        "websockets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BabbleCast",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
