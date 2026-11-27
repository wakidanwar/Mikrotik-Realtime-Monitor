"""Collapsible dashboard widgets and the three-beep alarm."""

import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

import app.ui as ui_module
from app.collector import MonitorState
from app.config import AppConfig, InterfaceConfig
from app.ui import CollapsibleCard, MonitorWindow


def test_collapsible_card_toggles_to_icon_and_back():
    app = QApplication.instance() or QApplication([])
    body = QWidget()
    card = CollapsibleCard("system", "System", "CPU, RAM, suhu, voltase", "fa5s.microchip", body)

    assert not card.is_collapsed()
    assert not card.toggle_btn.icon().isNull()
    assert "System" in card.toolTip()

    card.set_collapsed(True, animate=False)
    assert card.is_collapsed()
    assert not card.toggle_btn.icon().isNull()
    assert body.isHidden()
    assert not card.icon_btn.isHidden()

    card.set_collapsed(False, animate=False)
    assert not card.is_collapsed()
    assert not body.isHidden()
    assert card.icon_btn.isHidden()


def test_collapsing_all_left_widgets_shrinks_chart_area():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    config.interfaces = [InterfaceConfig(name="ether1", label="UPLINK")]
    window = MonitorWindow(config, MonitorState(config))

    assert window.left_scroll.width() == 340
    for key in ("system", "latency", "users"):
        window.collapsibles[key].set_collapsed(True, animate=False)

    assert window.left_scroll.width() <= 60


def test_alarm_uses_mp3_once(monkeypatch, tmp_path):
    audio = tmp_path / "audio-alarm.mp3"
    audio.write_bytes(b"mp3")
    monkeypatch.setattr(ui_module, "resource_path", lambda _: audio)

    played = []

    class FakePlayer:
        def play(self, path, times=1):
            played.append((path, times))

    monkeypatch.setattr(ui_module, "_alarm_player", FakePlayer())

    ui_module._play_alarm()

    assert played == [(audio, 1)]


def test_alarm_falls_back_to_one_beep_without_file(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ui_module, "resource_path", lambda _: tmp_path / "missing.mp3")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", types.SimpleNamespace(
        Beep=lambda freq, duration: calls.append((freq, duration)),
    ))
    monkeypatch.setattr(ui_module.QTimer, "singleShot", lambda *args, **kwargs: args[-1]())

    ui_module._play_alarm()

    assert len(calls) == 1
