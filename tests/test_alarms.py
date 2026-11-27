"""Alarm rule storage and matching are independent of the UI."""

import sys


def test_user_dir_uses_localappdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from app.paths import user_dir

    assert user_dir() == tmp_path / "MikroTik-Realtime-Monitor"


def test_user_path_resolves_inside_user_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from app.paths import user_path

    assert user_path("alarms/sound.mp3") == tmp_path / "MikroTik-Realtime-Monitor" / "alarms" / "sound.mp3"


def test_rule_matches_message_case_insensitively():
    from app.alarms import AlarmRule, rule_matches

    rule = AlarmRule(id="radius", phrase="Radius Server Is Not Responding")

    assert rule_matches({"message": "radius server is not responding now"}, rule)
    assert not rule_matches({"message": "radius server replied"}, rule)
    assert not rule_matches({"message": "x"}, AlarmRule(id="empty", phrase="  "))


def test_first_matching_rule_fires_and_cooldown_blocks_repeat():
    from app.alarms import AlarmRule, evaluate_entries

    rules = [
        AlarmRule(id="a", phrase="down", cooldown_s=30),
        AlarmRule(id="b", phrase="down", cooldown_s=30),
    ]
    seen, cooldowns = set(), {}

    first = [{"time": "10:00", "message": "link down"}]
    assert [r.id for r in evaluate_entries(first, rules, seen, 100.0, cooldowns)] == ["a"]
    assert evaluate_entries(first, rules, seen, 200.0, cooldowns) == []

    inside_cooldown = [{"time": "10:01", "message": "still down"}]
    assert evaluate_entries(inside_cooldown, rules, seen, 110.0, cooldowns) == []
    assert ("b", "10:01", "still down") in seen

    after_cooldown = [{"time": "10:02", "message": "down again"}]
    assert [r.id for r in evaluate_entries(after_cooldown, rules, seen, 140.0, cooldowns)] == ["a"]


def test_master_switch_off_marks_seen_but_fires_nothing():
    from app.alarms import AlarmRule, evaluate_entries

    rules = [AlarmRule(id="a", phrase="down")]
    seen, cooldowns = set(), {}
    entries = [{"time": "10:00", "message": "link down"}]

    assert evaluate_entries(entries, rules, seen, 100.0, cooldowns, master_on=False) == []
    assert ("a", "10:00", "link down") in seen


def test_alarm_store_defaults_and_round_trip(tmp_path, monkeypatch):
    from app.alarms import AlarmStore

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    store = AlarmStore()

    settings = store.load()
    assert [r.phrase for r in settings.log_rules] == ["radius server is not responding"]
    assert settings.log_rules[0].sound == "bundled:assets/audio-alarm.mp3"
    assert settings.ping_warning_sound == "bundled:assets/warning.mp3"

    settings.log_rules[0].phrase = "gateway down"
    store.save(settings)
    assert AlarmStore().load().log_rules[0].phrase == "gateway down"


def test_alarm_store_falls_back_to_defaults_for_corrupt_file(tmp_path, monkeypatch):
    from app.alarms import AlarmStore

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = tmp_path / "MikroTik-Realtime-Monitor" / "alarm_rules.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    assert AlarmStore().load().log_rules[0].phrase == "radius server is not responding"
