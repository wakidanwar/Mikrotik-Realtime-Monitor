"""Portable builds must read/write beside the .exe, not inside _MEIPASS."""

import sys
from pathlib import Path

import app.paths as paths


def test_resource_path_falls_back_to_bundled_assets(tmp_path, monkeypatch):
    bundled = tmp_path / "bundle"
    (bundled / "assets").mkdir(parents=True)
    icon = bundled / "assets" / "icon.png"
    icon.write_bytes(b"png")
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Portable" / "app.exe"), raising=False)

    assert paths.resource_path("assets/icon.png") == icon


def test_source_run_uses_project_root():
    assert paths.app_dir() == Path(paths.__file__).resolve().parent.parent


def test_frozen_run_uses_executable_folder(monkeypatch):
    fake_exe = Path("C:/Portable/Mikrotik-Realtime-Monitor.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)

    assert paths.app_dir() == fake_exe.parent
