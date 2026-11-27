"""User-editable alarm rules for MikroTik log entries."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.paths import user_dir

DEFAULT_ALARM_SOUND = "bundled:assets/audio-alarm.mp3"
DEFAULT_WARNING_SOUND = "bundled:assets/warning.mp3"
DEFAULT_PHRASE = "radius server is not responding"


@dataclass
class AlarmRule:
    id: str
    phrase: str
    name: str = ""
    enabled: bool = True
    sound: str = DEFAULT_ALARM_SOUND
    cooldown_s: float = 30.0


@dataclass
class AlarmSettings:
    log_rules: list[AlarmRule] = field(default_factory=list)
    ping_warning_enabled: bool = True
    ping_warning_sound: str = DEFAULT_WARNING_SOUND


class AlarmStore:
    """Loads and saves ``alarm_rules.json`` in the per-user data folder."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else user_dir() / "alarm_rules.json"

    @staticmethod
    def default() -> AlarmSettings:
        return AlarmSettings(
            log_rules=[
                AlarmRule(
                    id="radius",
                    phrase=DEFAULT_PHRASE,
                    name="RADIUS failure",
                    sound=DEFAULT_ALARM_SOUND,
                    cooldown_s=30.0,
                )
            ],
        )

    def load(self) -> AlarmSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self.default()
        if not isinstance(data, dict) or "log_rules" not in data:
            return self.default()
        rules = [
            _rule_from_data(item)
            for item in data.get("log_rules") or []
            if isinstance(item, dict)
        ]
        return AlarmSettings(
            log_rules=[rule for rule in rules if rule is not None],
            ping_warning_enabled=bool(data.get("ping_warning_enabled", True)),
            ping_warning_sound=str(
                data.get("ping_warning_sound") or DEFAULT_WARNING_SOUND
            ),
        )

    def save(self, settings: AlarmSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(settings)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


def _rule_from_data(data: dict[str, Any]) -> AlarmRule | None:
    rule_id = str(data.get("id") or "").strip()
    phrase = str(data.get("phrase") or "").strip()
    if not rule_id or not phrase:
        return None
    try:
        cooldown = float(data.get("cooldown_s", 30.0))
    except (TypeError, ValueError):
        cooldown = 30.0
    return AlarmRule(
        id=rule_id,
        phrase=phrase,
        name=str(data.get("name") or ""),
        enabled=bool(data.get("enabled", True)),
        sound=str(data.get("sound") or DEFAULT_ALARM_SOUND),
        cooldown_s=max(0.0, cooldown),
    )


def rule_matches(entry: dict[str, Any], rule: AlarmRule) -> bool:
    """A rule fires on a case-insensitive substring of the log message."""
    needle = (rule.phrase or "").strip().lower()
    if not needle:
        return False
    return needle in str(entry.get("message", "") or "").lower()


def evaluate_entries(
    entries: Iterable[dict[str, Any]],
    rules: Iterable[AlarmRule],
    seen: set[tuple[str, str, str]],
    now: float,
    cooldowns: dict[str, float],
    master_on: bool = True,
) -> list[AlarmRule]:
    """Return the first matching rule that is allowed to fire."""
    for entry in entries:
        matched = [rule for rule in rules if rule.enabled and rule_matches(entry, rule)]
        if not matched:
            continue
        time = str(entry.get("time", "") or "")
        message = str(entry.get("message", "") or "")
        keys = [(rule.id, time, message) for rule in matched]
        if keys[0] in seen:
            continue
        seen.update(keys)
        first = matched[0]
        if not master_on:
            continue
        last_fired = cooldowns.get(first.id)
        if last_fired is not None and now - last_fired < first.cooldown_s:
            continue
        cooldowns[first.id] = now
        return [first]
    return []
