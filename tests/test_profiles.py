"""Profile storage must keep passwords protected, including legacy files."""

import json
import sys

from app.config import OidsConfig
from app.profiles import ProfileStore, RouterProfile


def _write_legacy_store(path, password="plain-secret"):
    payload = {
        "active": "r1",
        "profiles": [{
            "name": "r1",
            "host": "192.0.2.1",
            "login": "admin",
            "password": password,
            "community": "public",
            "api_port": 8728,
            "api_use_ssl": False,
            "ros_version": "V7",
            "snmp_version": 2,
            "interfaces": [],
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_loading_a_legacy_plaintext_password_migrates_it(tmp_path):
    path = tmp_path / "routers.json"
    _write_legacy_store(path)

    store = ProfileStore(str(path))

    # The app can still use the password after loading.
    assert store.profiles[0].password == "plain-secret"

    # The on-disk copy is no longer the raw secret (on Windows: DPAPI).
    stored = json.loads(path.read_text(encoding="utf-8"))["profiles"][0]["password"]
    if sys.platform == "win32":
        assert stored.startswith("dpapi:")
    else:
        assert stored == "plain-secret"  # no DPAPI off Windows


def test_saving_a_profile_encrypts_the_password(tmp_path):
    path = tmp_path / "routers.json"
    store = ProfileStore(str(path))
    store.add_or_update(RouterProfile(name="r2", host="192.0.2.2", password="s3cret"))

    stored = json.loads(path.read_text(encoding="utf-8"))["profiles"][0]["password"]
    if sys.platform == "win32":
        assert stored.startswith("dpapi:")
    else:
        assert stored == "s3cret"


def test_old_profile_keeps_current_hardcoded_defaults(tmp_path):
    path = tmp_path / "routers.json"
    _write_legacy_store(path)

    profile = ProfileStore(str(path)).active_profile()
    config = ProfileStore.to_appconfig(profile)

    assert config.router.snmp.port == 161
    assert config.router.api.interval == 2.0
    assert config.polling.interval == 1.0
    assert config.polling.history_seconds == 120
    assert config.ping.interval == 1.0
    assert config.ping.timeout_ms == 1000
    assert config.ping.window == 60
    assert [target.host for target in config.ping.targets] == ["8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1"]
    assert config.oids.temperature == OidsConfig().temperature


def test_advanced_fields_round_trip_into_appconfig(tmp_path):
    path = tmp_path / "routers.json"
    store = ProfileStore(str(path))
    profile = RouterProfile(
        name="r3",
        host="192.0.2.3",
        snmp_port=1161,
        snmp_timeout=2.5,
        snmp_retries=3,
        api_interval=5.0,
        polling_interval=0.5,
        history_seconds=300,
        ping_interval=2.0,
        ping_timeout_ms=500,
        ping_window=120,
        oid_temperature="1.2.3",
        oid_voltage="1.2.4",
        oid_cpu="1.2.5",
        oid_active_users="1.2.6",
    )
    store.add_or_update(profile)

    loaded = ProfileStore(str(path)).active_profile()
    config = ProfileStore.to_appconfig(loaded)

    assert loaded.snmp_port == 1161
    assert config.router.snmp.timeout == 2.5
    assert config.router.api.interval == 5.0
    assert config.polling.history_seconds == 300
    assert config.ping.timeout_ms == 500
    assert config.oids.temperature == "1.2.3"
    assert config.oids.active_users == "1.2.6"
