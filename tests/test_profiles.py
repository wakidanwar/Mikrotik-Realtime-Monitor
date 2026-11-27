"""Profile storage must keep passwords protected, including legacy files."""

import json
import sys

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
