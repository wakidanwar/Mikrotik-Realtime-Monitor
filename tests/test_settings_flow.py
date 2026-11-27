"""Settings gear opens a non-destructive panel and applies changes live."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import main as main_module
from app.collector import MonitorState
from app.config import AppConfig
from app.profiles import ProfileStore
from app.setup import SetupWindow
from app.ui import HeaderBar, MonitorWindow


def test_settings_close_hides_without_quitting(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = SetupWindow(ProfileStore(str(tmp_path / "routers.json")))
    window.set_settings_mode(None, readonly=True)
    quit_calls = []
    window.on_quit = lambda: quit_calls.append(1)
    window.showMaximized()

    window.close()

    assert quit_calls == []
    assert not window.isVisible()


def test_settings_mode_hides_profile_actions_and_shows_apply(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = SetupWindow(ProfileStore(str(tmp_path / "routers.json")))

    window.set_settings_mode(None, readonly=True)

    assert window.btn_connect.isHidden()
    assert window.btn_save.isHidden()
    assert window.btn_new.isHidden()
    assert window.btn_delete.isHidden()
    assert not window.btn_apply.isHidden()
    assert not window.tabs.isTabEnabled(0)
    assert window.tabs.isTabEnabled(2)


def test_show_tab_selects_alarm_tab(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = SetupWindow(ProfileStore(str(tmp_path / "routers.json")))

    window.show_tab("Alarm")

    assert window.tabs.tabText(window.tabs.currentIndex()) == "Alarm"


def test_apply_config_emits_live_apply_signal():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    window = MonitorWindow(config, MonitorState(config))
    seen = []
    window.config_applied.connect(seen.append)

    window.apply_config(config)

    assert seen == [config]


def test_header_settings_button_forwards_to_monitor_window():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    window = MonitorWindow(config, MonitorState(config))
    seen = []
    window.settings_requested.connect(lambda: seen.append(1))

    assert window.header.settings_btn is not None
    window.header.settings_btn.click()

    assert seen == [1]


def test_controller_rebuilds_dashboard_on_live_apply(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_module.MonitorWindow, "start", lambda self, demo=False: None)
    monkeypatch.setattr(main_module.MonitorWindow, "stop", lambda self: None)
    controller = main_module._install_controllers(app, ProfileStore(str(tmp_path / "routers.json")))
    controller["direct"] = True

    first = controller["build_dashboard"](AppConfig(), demo=True)
    first.settings_requested.emit()

    setup = controller["setup"]
    assert not setup.tabs.isTabEnabled(0)
    assert setup.tabs.isTabEnabled(2)

    updated = AppConfig()
    updated.router.host = "192.0.2.10"
    setup.settings_applied.emit(updated)

    assert controller["dashboard"] is not first
    assert controller["dashboard"].config.router.host == "192.0.2.10"


def test_header_button_order_places_settings_before_disconnect():
    app = QApplication.instance() or QApplication([])
    header = HeaderBar(AppConfig())

    layout = header.layout()
    assert not header.settings_btn.isHidden()
    assert header.settings_btn.text() == "Settings"
    assert layout.indexOf(header.settings_btn) < layout.indexOf(header.setup_btn)
