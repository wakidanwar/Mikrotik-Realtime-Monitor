"""Locate the application folder in both source and frozen builds."""

from __future__ import annotations

import os
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


def user_dir() -> Path:
    """Writable folder for per-user settings such as alarm rules and audio."""
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "MikroTik-Realtime-Monitor"
    return app_dir() / ".userdata"


def user_path(relative: str) -> Path:
    """Resolve a relative user-data path without allowing absolute escapes."""
    parts = [part for part in str(relative).replace("\\", "/").split("/") if part not in ("", ".", "..")]
    return user_dir().joinpath(*parts)

