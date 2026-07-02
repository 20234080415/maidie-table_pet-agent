# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)

# Whole directories are collected so new sprites, actions, and documentation are
# packaged automatically. Keep secrets out of packaging/config.json.
datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "docs"), "docs"),
    (str(project_root / "README.md"), "."),
    (str(project_root / "packaging" / "config.json"), "config"),
]

hiddenimports = collect_submodules("core.plugins")

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Maidie",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Maidie",
)
