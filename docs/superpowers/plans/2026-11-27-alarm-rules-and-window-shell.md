# Alarm Rules and Window Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make alarm rules, custom audio, advanced settings, and OS-native maximized windows fully manageable from the app UI, with RouterOS-only log alarms and live apply.

**Architecture:** Add a small global alarm-rule store under user data, keep `config.yaml` as the authoritative CLI override, and route Settings through the existing `SetupWindow` in a non-destructive mode. Live apply recreates the dashboard window from the new config so all widgets, collectors, and history restart consistently.

**Tech Stack:** Python 3, PySide6/QtWidgets, PyYAML, JSON dataclasses, pytest offscreen, PyInstaller onefile.

**Spec:** `docs/superpowers/specs/2026-11-27-alarm-rules-and-window-shell-design.md`

## Global Constraints

- Windows 10/11 64-bit; PyInstaller onefile from `build_exe.bat`.
- No new third-party dependency.
- `config.yaml`, `routers.json`, user data, custom audio, `build/`, `dist/`, `Release/`, `*.exe`, `*.zip` must never be committed.
- Bundled sounds stay at `assets/audio-alarm.mp3` and `assets/warning.mp3`; frozen EXE resolves them via `resource_path`.
- User files go under `user_dir()` (`%LOCALAPPDATA%\MikroTik-Realtime-Monitor`, fallback `app_dir()/".userdata"`), never under `assets/`.
- Alarm log rules apply only when `config.router.device_type == "routeros"` or `ros_version in {"V6", "V7"}`. SwOS/other SNMP use ping warning only.
- One log entry fires the first matching enabled rule only. Single `AlarmPlayer`, no queue.
- Tests run with `QT_QPA_PLATFORM=offscreen`; keep the full suite green after every task.

## Review Focus

- SwOS log containing "radius server is not responding" → no log alarm. Test: Task 2 router-gating test.
- One log entry matching two enabled rules → first rule in list order plays once. Test: Task 1 `evaluate_entries` test.
- Custom audio filename like `../../evil.mp3` or size > 2 MB → rejected, no file copied. Test: Task 3 upload validation test.
- Bundled or custom audio file missing → fallback beep, no exception. Test: Task 2 missing-file test.
- Settings Close with dashboard running → hides panel, app keeps running. Test: Task 5 closeEvent test.
- Live apply in `--demo` mode → demo collector restarts with synthetic data, no SNMP. Test: Task 5 live-apply signal test.
- Existing `routers.json` without new advanced keys → loads with current defaults. Test: Task 4 backward-compatible load test.

---

### Task 1: User data paths and alarm rule store

**Files:**
- Modify: `app/paths.py`
- Create: `app/alarms.py`
- Modify: `.gitignore`
- Test: `tests/test_alarms.py`

**Interfaces:**
- Consumes: `app.paths.app_dir()`.
- Produces: `user_dir() -> Path`, `user_path(relative: str) -> Path`, `AlarmRule`, `AlarmSettings`, `AlarmStore(path: Path | None = None)`, `.load() -> AlarmSettings`, `.save(settings: AlarmSettings) -> None`, `rule_matches(entry: dict, rule: AlarmRule) -> bool`, `evaluate_entries(entries, rules, seen: set[tuple], now: float, cooldowns: dict[str, float], master_on: bool = True) -> list[AlarmRule]`.

- [ ] **Step 1: Write failing tests for paths and pure rule logic**

```python
def test_user_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from app.paths import user_dir
    assert user_dir() == tmp_path / "MikroTik-Realtime-Monitor"


def test_rule_matches_is_case_insensitive_substring():
    from app.alarms import AlarmRule, rule_matches
    rule = AlarmRule(id="r", phrase="Radius Server Is Not Responding")
    assert rule_matches({"message": "radius server is not responding now"}, rule)
    assert not rule_matches({"message": "radius replied"}, rule)
    assert not rule_matches({"message": "x"}, AlarmRule(id="e", phrase="  "))


def test_first_matching_rule_only_with_cooldown_and_seen():
    from app.alarms import AlarmRule, evaluate_entries
    rules = [
        AlarmRule(id="a", phrase="down", cooldown_s=30),
        AlarmRule(id="b", phrase="down", cooldown_s=30),
    ]
    seen, cooldowns = set(), {}
    entries = [{"time": "10:00", "message": "link down"}]
    assert [r.id for r in evaluate_entries(entries, rules, seen, 100.0, cooldowns)] == ["a"]
    # Same entry is already seen, so nothing fires again.
    assert evaluate_entries(entries, rules, seen, 200.0, cooldowns) == []
    # New entry inside cooldown is marked seen but does not fire.
    entries2 = [{"time": "10:01", "message": "still down"}]
    assert evaluate_entries(entries2, rules, seen, 110.0, cooldowns) == []
    assert ("b", "10:01", "still down") in seen
    # New entry after cooldown fires again, first rule still wins.
    entries3 = [{"time": "10:02", "message": "down again"}]
    assert [r.id for r in evaluate_entries(entries3, rules, seen, 140.0, cooldowns)] == ["a"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alarms.py -q`  
Expected: FAIL with `ModuleNotFoundError: No module named 'app.alarms'`.

- [ ] **Step 3: Implement user paths**

In `app/paths.py`, add `user_dir()` returning `%LOCALAPPDATA%\MikroTik-Realtime-Monitor` on Windows when the env var exists, otherwise `app_dir()/".userdata"`; add `user_path(relative)` joining `user_dir()` with a relative POSIX-style path. Do not create directories there yet; `AlarmStore.save()` creates parents.

- [ ] **Step 4: Implement alarm dataclasses and store**

In `app/alarms.py`, define `AlarmRule` with fields exactly `id, phrase, name="", enabled=True, sound="bundled:assets/audio-alarm.mp3", cooldown_s=30.0`; `AlarmSettings` with `log_rules`, `ping_warning_enabled=True`, `ping_warning_sound="bundled:assets/warning.mp3"`. `AlarmStore.default()` returns one RADIUS rule and the ping warning default. `load()` reads `user_dir()/"alarm_rules.json"`, falling back to default when missing or malformed. `save()` writes JSON with UTF-8 and `parents=True`. `evaluate_entries()` adds every matched rule key to `seen`, fires only the first rule whose cooldown has elapsed, updates `cooldowns[rule.id]` only when firing, and returns immediately after the first fired rule.

- [ ] **Step 5: Add ignore rules**

Append `.userdata/`, `alarm_rules.json`, and `user_data/` to `.gitignore`.

- [ ] **Step 6: Run tests and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alarms.py -q`  
Expected: PASS.  
Commit: `git add app/paths.py app/alarms.py .gitignore tests/test_alarms.py && git commit -m "feat: add user-scoped alarm rule store"`

---

### Task 2: Wire alarm rules into log and ping alarms

**Files:**
- Modify: `app/ui.py:448-460,493-537,1304-1310,1480-1503`
- Modify: `tests/test_left_panel.py:85-88,135-149`
- Modify: `tests/test_dashboard_extras.py`
- Modify: `tests/test_collapsible.py`

**Interfaces:**
- Consumes: Task 1 `AlarmStore`, `AlarmSettings`, `evaluate_entries`, `user_path`.
- Produces: `_play_sound(choice: str, holder_name: str = "_alarm_player") -> None`, `MonitorWindow.alarm_settings`, `MonitorWindow._alarm_cooldowns`.

- [ ] **Step 1: Write failing tests**

In `tests/test_left_panel.py`, replace `_should_alarm()` assertions with `alarm.rule_matches()` using a RADIUS rule. Add a test where a SwOS config with the same log message never calls the alarm player. In `tests/test_dashboard_extras.py`, add a test that `_play_sound("custom:missing.mp3", "_alarm_player")` calls the fallback without raising.

- [ ] **Step 2: Run focused tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_left_panel.py tests/test_dashboard_extras.py -q`  
Expected: FAIL because `_should_alarm` / `_play_sound` do not exist yet.

- [ ] **Step 3: Replace hardcoded alarm logic**

Remove `RADIUS_ALARM_TEXT` and `_should_alarm()`. In `MonitorWindow.__init__`, load `self.alarm_settings = AlarmStore().load()` and init `self._alarm_cooldowns = {}`. In `_update_logs()`, when the profile is RouterOS, call `evaluate_entries(...)` and play the returned rule's `sound`; for SwOS/other SNMP skip the block. Keep `_alarm_seen` with the new `(rule.id, time, message)` key and cleanup at 200.

- [ ] **Step 4: Add sound resolver and keep wrappers**

Implement `_play_sound(choice, holder_name)`: `bundled:<relative>` → `resource_path(relative)`; `custom:<relative>` → `user_path(relative)`; unknown → no file. Reuse `_play_audio_once()` fallback. `_play_alarm()` and `_play_warning()` call `_play_sound()` with the bundled defaults. `_check_dns_warning()` uses `self.alarm_settings.ping_warning_sound` and respects `ping_warning_enabled`.

- [ ] **Step 5: Run focused and full tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_left_panel.py tests/test_dashboard_extras.py tests/test_collapsible.py -q` then `.venv\Scripts\python.exe -m pytest tests -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

Commit: `git add app/ui.py tests/test_left_panel.py tests/test_dashboard_extras.py tests/test_collapsible.py && git commit -m "feat: evaluate log alarms from configurable rules"`

---

### Task 3: Alarm tab with rule management and audio upload

**Files:**
- Modify: `app/setup.py`
- Create: `tests/test_alarm_settings_ui.py`

**Interfaces:**
- Consumes: Task 2 `AlarmStore`, `AlarmSettings`, `_play_sound`.
- Produces: `SetupWindow.alarm_rules_table`, `SetupWindow.ping_enabled_check`, `SetupWindow.ping_sound_combo`, `SetupWindow._collect_alarm_settings() -> AlarmSettings`, `SetupWindow._load_alarm_settings(settings: AlarmSettings) -> None`, `SetupWindow._upload_audio() -> str | None`.

- [ ] **Step 1: Write failing UI tests**

```python
def test_upload_rejects_unsafe_names_and_large_files(monkeypatch, tmp_path):
    from app import setup as setup_module
    monkeypatch.setattr(setup_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "../../evil.mp3"), ""))
    window = setup_module.SetupWindow.__new__(setup_module.SetupWindow)
    assert window._validate_audio_upload(tmp_path / "evil.mp3") is None
    big = tmp_path / "big.mp3"
    big.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    assert window._validate_audio_upload(big) is None
```

- [ ] **Step 2: Run focused test to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alarm_settings_ui.py -q`  
Expected: FAIL because `_validate_audio_upload` does not exist.

- [ ] **Step 3: Build the Alarm tab**

In `SetupWindow._build_ui()`, introduce `QTabWidget` with tabs `Koneksi`, `Interface`, `Alarm`, `Lanjutan`. Move the existing connection form and interface group into the first two tabs without changing their widget names. Add an Alarm tab containing a `QTableWidget` with columns `Enable`, `Kata/Kalimat`, `Suara`, `Cooldown`, `Test`, and buttons `Add rule`, `Upload audio`, `Remove`, `Apply`; add the ping warning checkbox and sound combo below the table.

- [ ] **Step 4: Implement validation and persistence helpers**

`_validate_audio_upload(path: Path) -> Path | None` checks extension in `{".mp3", ".wav", ".ogg"}` and size ≤ 2 MB; returns the path or `None`. `_upload_audio()` copies an accepted file to `user_dir()/alarms/<uuid4>.<ext>` and returns the relative string `alarms/<uuid>.<ext>`. `_collect_alarm_settings()` reads the table into `AlarmSettings`; `_load_alarm_settings()` fills it. `Apply` saves via `AlarmStore().save()` and emits `settings_applied` with the current config.

- [ ] **Step 5: Run tests and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alarm_settings_ui.py -q` then full suite.  
Expected: PASS.  
Commit: `git add app/setup.py tests/test_alarm_settings_ui.py && git commit -m "feat: manage alarm rules and custom audio from UI"`

---

### Task 4: Advanced per-profile settings and interface capacity

**Files:**
- Modify: `app/profiles.py:34-52,168-210`
- Modify: `app/setup.py`
- Modify: `tests/test_profiles.py`

**Interfaces:**
- Consumes: `InterfaceChoice`, `RouterProfile`, `ProfileStore`.
- Produces: extended `RouterProfile` fields and `ProfileStore.to_appconfig()` honoring them.

- [ ] **Step 1: Write failing backward-compatibility test**

```python
def test_old_profile_defaults_match_current_hardcoded_config():
    from app.config import OidsConfig
    from app.profiles import ProfileStore, RouterProfile
    old = {"profiles": [{"name": "r", "host": "192.0.2.1", "ros_version": "V7", "snmp_version": 2}], "active": "r"}
    import json, tmp_path
    path = tmp_path / "routers.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    profile = ProfileStore(str(path)).active_profile()
    cfg = ProfileStore.to_appconfig(profile)
    assert cfg.polling.interval == 1.0
    assert cfg.polling.history_seconds == 120
    assert cfg.api.interval == 2.0
    assert cfg.oids.temperature == OidsConfig().temperature
```

- [ ] **Step 2: Run focused test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_profiles.py -q`  
Expected: FAIL on missing advanced behavior/field access.

- [ ] **Step 3: Extend profile fields and conversion**

Add optional fields to `RouterProfile` with defaults matching Task 1 values: `snmp_port=161`, `snmp_timeout=1.0`, `snmp_retries=1`, `api_interval=2.0`, `polling_interval=1.0`, `history_seconds=120`, `ping_interval=1.0`, `ping_timeout_ms=1000`, `ping_window=60`, `ping_targets` default four public DNS targets, and OID strings from `OidsConfig()`. `ProfileStore.load()` uses `.get()` with those defaults. `to_appconfig()` passes them into `SnmpConfig`, `ApiConfig`, `PollingConfig`, `PingConfig`, and `OidsConfig`.

- [ ] **Step 4: Fill Lanjutan and Interface widgets**

In `setup.py`, `_load_profile()` and `_collect_profile()` read/write the new fields. Add `max_mbps` spinbox per monitored interface in the Interface tab, writing to `InterfaceChoice.max_mbps`.

- [ ] **Step 5: Run tests and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_profiles.py -q` then full suite.  
Expected: PASS.  
Commit: `git add app/profiles.py app/setup.py tests/test_profiles.py && git commit -m "feat: save advanced settings per router profile"`

---

### Task 5: Settings mode and live apply

**Files:**
- Modify: `app/ui.py:958-1010,1104-1165`
- Modify: `app/setup.py:50-72,583-614`
- Modify: `main.py:30-132`
- Create: `tests/test_settings_flow.py`

**Interfaces:**
- Consumes: Task 3 `settings_applied`, Task 4 profile conversion.
- Produces: `HeaderBar.settings_clicked`, `MonitorWindow.settings_requested`, `MonitorWindow.config_applied = Signal(object)`, `MonitorWindow.apply_config(config: AppConfig)`, `SetupWindow.set_settings_mode(base_config: AppConfig | None, readonly: bool)`, `SetupWindow.show_tab(name: str)`.

- [ ] **Step 1: Write failing tests**

```python
def test_settings_close_hides_without_quitting(monkeypatch, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.setup import SetupWindow
    from app.profiles import ProfileStore
    app = QApplication.instance() or QApplication([])
    window = SetupWindow(ProfileStore(str(tmp_path / "routers.json")))
    window.set_settings_mode(None, readonly=True)
    quit_calls = []
    window.on_quit = lambda: quit_calls.append(1)
    window.close()
    assert quit_calls == []
    assert not window.isVisible()


def test_apply_config_emits_signal():
    from app.collector import MonitorState
    from app.config import AppConfig
    from app.ui import MonitorWindow
    app = QApplication.instance() or QApplication([])
    window = MonitorWindow(AppConfig(), MonitorState(AppConfig()))
    seen = []
    window.config_applied.connect(seen.append)
    cfg = AppConfig()
    window.apply_config(cfg)
    assert seen == [cfg]
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings_flow.py -q`  
Expected: FAIL because the new signals/methods do not exist.

- [ ] **Step 3: Add Settings entry point**

Add gear `Settings` button to `HeaderBar` before `Disconnect`, emitting `settings_clicked`. In `MonitorWindow`, forward `settings_requested` and define `apply_config(config)` that only emits `config_applied(config)`; do not stop workers there.

- [ ] **Step 4: Add non-destructive SetupWindow mode**

`set_settings_mode(base_config, readonly)` stores `base_config`, hides `btn_connect/btn_save/btn_new/btn_delete`, shows `btn_apply`, and makes connection/interface/Lanjutan widgets read-only when `readonly`. `show_tab(name)` selects the named tab. `closeEvent()` calls `hide()` and skips `on_quit` when in settings mode. `Apply` saves alarm rules and emits `settings_applied(config)`: profile-derived config in normal mode, `base_config` unchanged in demo/`--config` mode.

- [ ] **Step 5: Wire main.py for live apply**

Add `controller["demo"]` flag. `rebuild_dashboard(config)` stops/closes the old dashboard with `_disconnecting=True`, builds a new `MonitorState(config)`/`MonitorWindow`, connects both settings and setup signals, `showMaximized()`, and `start(demo=controller["demo"])`. Connect `dash.settings_requested.connect(show_settings)` and `dash.config_applied.connect(rebuild_dashboard)`. `show_settings()` reuses/creates `SetupWindow` and calls `set_settings_mode()` accordingly.

- [ ] **Step 6: Run tests and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings_flow.py -q` then full suite.  
Expected: PASS.  
Commit: `git add app/ui.py app/setup.py main.py tests/test_settings_flow.py && git commit -m "feat: open settings from dashboard and apply live"`

---

### Task 6: Native window controls and maximized startup

**Files:**
- Modify: `app/ui.py:1-110,1532-1538`
- Modify: `main.py:67,86,108,115,128`
- Create: `tests/test_window_shell.py`

**Interfaces:**
- Consumes: `TitleBar`, `FramelessMixin`.
- Produces: `TitleBar` without custom min/max/close buttons; all windows shown with `showMaximized()`.

- [ ] **Step 1: Write failing tests**

```python
def test_title_bar_has_no_custom_window_buttons():
    from app.ui import TitleBar
    bar = TitleBar("t", "c")
    assert not hasattr(bar, "min_btn")
    assert not hasattr(bar, "max_btn")
    assert not hasattr(bar, "close_btn")


def test_window_flags_are_native(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget
    from app.ui import FramelessMixin
    app = QApplication.instance() or QApplication([])
    class W(FramelessMixin, QWidget): pass
    w = W()
    w.setup_frameless()
    assert not (w.windowFlags() & Qt.FramelessWindowHint)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_window_shell.py -q`  
Expected: FAIL because custom buttons/frameless flag still exist.

- [ ] **Step 3: Remove custom window chrome**

Delete the three `QPushButton`s and their drag/double-click handlers from `TitleBar`; keep title/context styling. Change `FramelessMixin.setup_frameless()` to native hints without `FramelessWindowHint`. Remove now-unused `QSizeGrip` imports from the top and widget import block in `app/ui.py`.

- [ ] **Step 4: Maximize every window**

Replace `show()` with `showMaximized()` at demo, `--config`, setup, and log-detail sites; `main.py:128` already uses it. Ensure `setWindowTitle()` remains so the OS title bar shows the right name.

- [ ] **Step 5: Run tests and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_window_shell.py -q` then full suite.  
Expected: PASS.  
Commit: `git add app/ui.py main.py tests/test_window_shell.py && git commit -m "refactor: use native window controls and maximized startup"`

---

### Task 7: Verify demo, real RouterOS, SwOS, build, push

**Files:**
- No product code changes expected; fix issues found in owning tasks.

**Interfaces:**
- Consumes: all previous tasks.

- [ ] **Step 1: Run full suite and static grep**

Run: `.venv\Scripts\python.exe -m pytest tests -q` and grep for `_should_alarm`, `RADIUS_ALARM_TEXT`, `FramelessWindowHint`, `show()` on windows.  
Expected: 0 failures, 0 stale references.

- [ ] **Step 2: Demo preview**

Run `main.py --demo`, capture screenshot, confirm gear exists, Settings opens maximized, alarm tab lists RADIUS rule, Close returns to dashboard. Confirm synthetic traffic still renders.

- [ ] **Step 3: Real RouterOS preview**

Run with the V7 RouterOS profile, confirm logs populate, change a rule phrase live, confirm dashboard restarts and log alarm follows the new phrase. Confirm active-user source stays `RouterOS API`.

- [ ] **Step 4: SwOS preview**

Run with a SwOS profile; inject or observe a log line containing the RADIUS phrase through the API feed if available; confirm no log alarm fires and ping warning remains active.

- [ ] **Step 5: Build EXE and inspect bundle**

Run `build_exe.bat`, verify exit 0 and PyInstaller TOC still contains `assets\audio-alarm.mp3` and `assets\warning.mp3`. Remove `build/`, `dist/`, `Release/`, `*.exe`, `*.spec` afterwards.

- [ ] **Step 6: Commit and push**

Run `git status --short`, confirm no secrets/artifacts, run `git push origin main`, then verify `git status -sb` shows `## main...origin/main` and local `main` equals `origin/main`.

## Self-Review

- Spec coverage: user-dir/store (T1), RouterOS gating/first-match/cooldown (T1+T2), custom audio (T3), advanced per-profile (T4), Settings mode/close/live apply (T5), native controls/maximize (T6), verification/push (T7).
- Type consistency: `AlarmSettings` and `AlarmRule` signatures are fixed in T1 and reused unchanged; `settings_applied`/`config_applied` carry `AppConfig`; `apply_config()` only emits the signal.
- Review Focus: each listed failure mode has a named test in its owning task.
- Proportion: plan states signatures, values, and tests without transcribing implementation bodies.
