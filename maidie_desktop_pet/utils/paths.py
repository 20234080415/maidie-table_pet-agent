from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    """Return a bundled resource in PyInstaller or a project file in development."""
    bundle_root = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    return bundle_root.joinpath(*parts)


def user_data_path(*parts: str) -> Path:
    """Return a writable path, isolated from the temporary PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "Maidie"
    else:
        base = PROJECT_ROOT
    return base.joinpath(*parts)
