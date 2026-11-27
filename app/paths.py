"""Locate the application folder in both source and frozen builds."""

from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """Project root when running from source; the .exe folder when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """Prefer a file beside the executable, then one bundled inside the exe."""
    beside_exe = app_dir() / relative
    if beside_exe.exists():
        return beside_exe
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidate = Path(bundled) / relative
        if candidate.exists():
            return candidate
    return beside_exe
