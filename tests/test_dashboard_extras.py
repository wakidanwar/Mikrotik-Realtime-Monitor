"""Extra dashboard controls: single-shot alarm, DNS warning, scale, fullscreen."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

import app.ui as ui_module
from app.collector import MonitorState
from app.config import AppConfig, PingTargetConfig
from app.ping import PingStats
from app.ui import (
    CollapsibleCard,
    MonitorWindow,
    _dns_loss_exceeded,
    clamp_ui_scale,
    scaled_qss,
)


class FakePlayer:
    def __init__(self):
        self.calls = []

    def play(self, path, times=1):
        self.calls.append((path, times))


def test_radius_alarm_plays_once(monkeypatch, tmp_path):
    audio = tmp_path / "audio-alarm.mp3"
    audio.write_bytes(b"mp3")
    requested = []

    def fake_resource_path(rel):
        requested.append(rel)
        return audio

    monkeypatch.setattr(ui_module, "resource_path", fake_resource_path)
    player = FakePlayer()
    monkeypatch.setattr(ui_module, "_alarm_player", player)

    ui_module._play_alarm()

    assert requested == ["assets/audio-alarm.mp3"]
    assert player.calls == [(audio, 1)]


def test_warning_alarm_uses_warning_mp3_once(monkeypatch, tmp_path):
    audio = tmp_path / "warning.mp3"
    audio.write_bytes(b"mp3")
    requested = []

    def fake_resource_path(rel):
        requested.append(rel)
        return audio

    monkeypatch.setattr(ui_module, "resource_path", fake_resource_path)
    player = FakePlayer()
    monkeypatch.setattr(ui_module, "_warning_player", player)

    ui_module._play_warning()

    assert requested == ["assets/warning.mp3"]
    assert player.calls == [(audio, 1)]


def test_dns_loss_helper_uses_one_percent_threshold():
    low = PingStats("DNS", "8.8.8.8", 10.0, 0.9, 10, 10.0)
    high = PingStats("DNS2", "1.1.1.1", 10.0, 1.1, 10, 10.0)
    assert _dns_loss_exceeded([low]) is False
    assert _dns_loss_exceeded([low, high]) is True
    assert _dns_loss_exceeded([]) is False


def test_dns_warning_fires_once_until_loss_recovers(monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    config.ping.targets = [PingTargetConfig(name="DNS", host="8.8.8.8")]
    window = MonitorWindow(config, MonitorState(config))
    played = []
    monkeypatch.setattr(ui_module, "_play_warning", lambda: played.append(1))

    bad = SimpleNamespace(pings=[PingStats("DNS", "8.8.8.8", 10.0, 2.0, 10, 10.0)])
    good = SimpleNamespace(pings=[PingStats("DNS", "8.8.8.8", 10.0, 0.0, 10, 10.0)])

    window._check_dns_warning(bad)
    window._check_dns_warning(bad)
    assert len(played) == 1

    window._check_dns_warning(good)
    window._check_dns_warning(bad)
    assert len(played) == 2


def test_ui_scale_is_clamped_between_75_and_125():
    assert clamp_ui_scale(50) == 75
    assert clamp_ui_scale(200) == 125
    assert clamp_ui_scale(100) == 100


def test_scaled_qss_changes_pixel_values():
    assert "11px" in ui_module.QSS
    assert "11px" not in scaled_qss(1.25)
    assert round(11 * 1.25) == 14


def test_header_exposes_fullscreen_and_scale_controls():
    app = QApplication.instance() or QApplication([])
    window = MonitorWindow(AppConfig(), MonitorState(AppConfig()))
    assert window.header.fullscreen_btn is not None
    assert window.header.scale_btn.text() == "100%"


def test_collapse_button_has_arrow_icon():
    app = QApplication.instance() or QApplication([])
    card = CollapsibleCard("system", "System", "detail", "fa5s.microchip", QWidget())
    assert not card.toggle_btn.icon().isNull()
