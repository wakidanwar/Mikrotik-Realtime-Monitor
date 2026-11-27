"""Windows use the operating system frame and open maximized."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import app.ui as ui_module
from app.collector import MonitorState
from app.config import AppConfig
from app.profiles import ProfileStore
from app.setup import SetupWindow


def test_monitor_and_setup_windows_have_native_title_bars(tmp_path):
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    monitor = ui_module.MonitorWindow(config, MonitorState(config))
    setup = SetupWindow(ProfileStore(str(tmp_path / "routers.json")))

    for window in (monitor, setup):
        assert not window.windowFlags() & Qt.FramelessWindowHint
        assert not hasattr(window.title_bar, "min_btn")
        assert not hasattr(window.title_bar, "max_btn")
        assert not hasattr(window.title_bar, "close_btn")


def test_log_detail_opens_maximized(monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    window = ui_module.MonitorWindow(config, MonitorState(config))
    calls = []
    monkeypatch.setattr(ui_module.LogDetailWindow, "showMaximized", lambda self: calls.append(1))
    monkeypatch.setattr(ui_module.LogDetailWindow, "show", lambda self: calls.append("show"))

    window._open_log_detail()

    assert calls == [1]
