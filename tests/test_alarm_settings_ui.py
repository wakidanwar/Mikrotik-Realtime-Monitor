"""Alarm tab: rule editing, upload validation, and persistence helpers."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.alarms import AlarmRule, AlarmSettings
from app.setup import SetupWindow


def test_upload_validation_rejects_unsafe_extension_and_large_file(tmp_path):
    window = SetupWindow.__new__(SetupWindow)

    unsafe = tmp_path / "evil.exe"
    unsafe.write_bytes(b"x")
    assert window._validate_audio_upload(unsafe) is None

    big = tmp_path / "big.mp3"
    big.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    assert window._validate_audio_upload(big) is None

    good = tmp_path / "clip.mp3"
    good.write_bytes(b"mp3")
    assert window._validate_audio_upload(good) == good


def test_upload_copies_audio_into_user_data(monkeypatch, tmp_path):
    from app import setup as setup_module

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    source = tmp_path / "clip.wav"
    source.write_bytes(b"wave")
    monkeypatch.setattr(
        setup_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(source), ""),
    )
    window = SetupWindow.__new__(SetupWindow)

    relative = window._upload_audio()

    assert relative and relative.startswith("alarms/") and relative.endswith(".wav")
    assert not os.path.isabs(relative)
    assert (tmp_path / "MikroTik-Realtime-Monitor" / relative).read_bytes() == b"wave"


def test_alarm_table_round_trip_preserves_rules_and_ping_sound():
    app = QApplication.instance() or QApplication([])
    window = SetupWindow.__new__(SetupWindow)
    window._build_alarm_tab_widgets()

    settings = AlarmSettings(
        log_rules=[
            AlarmRule(id="radius", phrase="radius down", sound="bundled:assets/warning.mp3", cooldown_s=15),
            AlarmRule(id="custom", phrase="link flap", sound="custom:alarms/flap.mp3", enabled=False),
        ],
        ping_warning_enabled=False,
        ping_warning_sound="custom:alarms/dns.mp3",
    )
    window._load_alarm_settings(settings)
    collected = window._collect_alarm_settings()

    assert [(r.phrase, r.sound, r.cooldown_s, r.enabled) for r in collected.log_rules] == [
        ("radius down", "bundled:assets/warning.mp3", 15.0, True),
        ("link flap", "custom:alarms/flap.mp3", 30.0, False),
    ]
    assert collected.ping_warning_enabled is False
    assert collected.ping_warning_sound == "custom:alarms/dns.mp3"
