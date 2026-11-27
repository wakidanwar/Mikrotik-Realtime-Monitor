"""Left-panel widgets: log rows and latency rows with missing samples."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import app.ui as ui_module
from app.alarms import AlarmRule, AlarmSettings, rule_matches
from app.collector import MonitorState
from app.config import AppConfig
from app.ping import PingStats
from app.routeros_api import ApiReading
from app.ui import (
    LogDetailWindow,
    MonitorWindow,
    PingRow,
    _filter_logs,
    _format_log_entry,
    _full_log_line,
    _short_log_time,
)


def test_log_entry_uses_short_time_and_elides_long_messages():
    line = _format_log_entry({
        "time": "09:12:04",
        "topics": "system,info",
        "message": "link up",
    })
    assert line.startswith("09:12")
    assert "system,info" in line
    assert line.endswith("link up")

    long_line = _format_log_entry({
        "time": "09:12:04",
        "topics": "pppoe,info",
        "message": "x" * 120,
    }, max_message=20)
    assert "…" in long_line
    assert len(long_line) < 80


def test_short_log_time_drops_seconds_and_shortens_date():
    assert _short_log_time("09:12:04") == "09:12"
    assert _short_log_time("2026-11-26 09:12:04") == "11-26 09:12"
    assert _short_log_time("") == "--:--"


def test_detail_window_keeps_full_time_and_message():
    app = QApplication.instance() or QApplication([])
    window = LogDetailWindow()
    window.set_logs([{
        "time": "2026-11-26 09:12:04",
        "topics": "system,info",
        "message": "a very long log message that must stay intact",
    }])
    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "2026-11-26 09:12:04"
    assert window.table.item(0, 2).text().endswith("must stay intact")
    assert window.title_bar.context_label.text() == "1 entries"


def test_ping_row_handles_no_samples_yet():
    app = QApplication.instance() or QApplication([])
    row = PingRow(SimpleNamespace(name="Google DNS", host="8.8.8.8"))

    row.update_stats(PingStats("Google DNS", "8.8.8.8", None, None, 0, None))

    assert row.avg_label.text() == "--"
    assert row.loss_label.text() == "loss --"


def test_full_log_line_is_copy_ready():
    line = _full_log_line({
        "time": "2026-11-26 09:12:04",
        "topics": "system,info",
        "message": "user admin logged in",
    })
    assert line == "2026-11-26 09:12:04\tsystem,info\tuser admin logged in"


def test_radius_rule_matches_only_that_message():
    rule = AlarmRule(id="radius", phrase="radius server is not responding")

    assert rule_matches({"message": "RADIUS server is not responding"}, rule)
    assert rule_matches({"message": "radius server is not responding now"}, rule)
    assert not rule_matches({"message": "RADIUS server replied"}, rule)
    assert not rule_matches({}, rule)


def test_detail_filter_searches_message_case_insensitively():
    logs = [
        {"message": "user admin logged in"},
        {"message": "RADIUS server is not responding"},
        {"message": "RADIUS authentication ok"},
    ]
    assert _filter_logs(logs, "radius") == [logs[1], logs[2]]
    assert _filter_logs(logs, "") == logs


def test_newest_log_appears_first_in_compact_list():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    state = MonitorState(config)
    window = MonitorWindow(config, state)
    state.set_logs([
        {"time": "09:12:04", "topics": "system", "message": "oldest"},
        {"time": "09:13:04", "topics": "system", "message": "newest"},
    ])

    window._update_logs(state.snapshot())

    assert window.logs_list.item(0).text().endswith("newest")
    assert window.logs_list.item(1).text().endswith("oldest")


def test_detail_filter_and_copy_use_full_log_text():
    app = QApplication.instance() or QApplication([])
    window = LogDetailWindow()
    window.set_logs([
        {"time": "09:12:04", "topics": "system", "message": "RADIUS server is not responding"},
        {"time": "09:13:04", "topics": "system", "message": "link up"},
    ])

    window.search_edit.setText("radius")
    assert window.table.rowCount() == 1
    assert window.table.item(0, 2).text() == "RADIUS server is not responding"

    window.table.selectRow(0)
    window.copy_selected()
    assert app.clipboard().text() == "09:12:04\tsystem\tRADIUS server is not responding"


def test_alarm_sounds_once_per_new_radius_log(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(ui_module, "_play_sound", lambda sound, holder=None: calls.append(sound))
    config = AppConfig()
    state = MonitorState(config)
    window = MonitorWindow(config, state)

    state.set_logs([{"time": "09:12:04", "message": "RADIUS server is not responding"}])
    window._update_logs(state.snapshot())
    window._update_logs(state.snapshot())
    assert calls == ["bundled:assets/audio-alarm.mp3"]

    window.alarm_btn.setChecked(False)
    assert window.alarm_btn.text() == "Alarm off"
    state.set_logs([
        {"time": "09:12:04", "message": "RADIUS server is not responding"},
        {"time": "09:14:04", "message": "RADIUS server is not responding"},
    ])
    window._update_logs(state.snapshot())
    assert len(calls) == 1


def test_swos_log_does_not_fire_log_alarm(monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    config.router.device_type = "swos"
    config.router.api.enabled = True
    state = MonitorState(config)
    window = MonitorWindow(config, state)
    window.alarm_settings = AlarmSettings(log_rules=[
        AlarmRule(id="radius", phrase="radius server is not responding"),
    ])
    calls = []
    monkeypatch.setattr(ui_module, "_play_sound", lambda sound, holder=None: calls.append(sound))

    state.set_logs([{"time": "09:12:04", "message": "RADIUS server is not responding"}])
    window._update_logs(state.snapshot())

    assert calls == []


def test_only_first_matching_rule_plays(monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    state = MonitorState(config)
    window = MonitorWindow(config, state)
    window.alarm_settings = AlarmSettings(log_rules=[
        AlarmRule(id="first", phrase="link down", sound="bundled:first.mp3"),
        AlarmRule(id="second", phrase="link down", sound="bundled:second.mp3"),
    ])
    calls = []
    monkeypatch.setattr(ui_module, "_play_sound", lambda sound, holder=None: calls.append(sound))

    state.set_logs([{"time": "09:12:04", "message": "link down"}])
    window._update_logs(state.snapshot())

    assert calls == ["bundled:first.mp3"]


def test_users_card_breaks_down_sessions_and_dhcp_usage():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    state = MonitorState(config)
    window = MonitorWindow(config, state)
    state.apply_api(ApiReading(
        active_users=60,
        pppoe_users=42,
        hotspot_users=18,
        dhcp_leases=170,
        dhcp_pool_used=170,
        dhcp_pool_size=200,
    ), 1000.0)

    window._refresh()

    assert window.pppoe_value.text() == "42"
    assert window.hotspot_value.text() == "18"
    assert window.dhcp_value.text() == "170 active"
    assert window.dhcp_pct.text() == "85%"
    assert "NEARLY FULL" in window.dhcp_warning.text()
    assert "170/200 IPs" in window.dhcp_warning.text()


def test_users_card_has_no_warning_when_pool_is_healthy():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    state = MonitorState(config)
    window = MonitorWindow(config, state)
    state.apply_api(ApiReading(dhcp_leases=50, dhcp_pool_used=50, dhcp_pool_size=200), 1000.0)

    window._refresh()

    assert window.dhcp_pct.text() == "25%"
    assert window.dhcp_warning.text() == "50/200 IPs"


def test_logs_card_shows_empty_state_when_api_is_off():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    state = MonitorState(config)
    window = MonitorWindow(config, state)

    window._update_logs(state.snapshot())

    assert window.logs_list.count() == 1
    assert window.logs_list.item(0).text() == "API disabled"
    assert window.logs_source_lbl.text() == "off"
