"""DPAPI protection must actually work, not silently fall back to plain text."""

import sys

from app.secrets import decrypt_password, encrypt_password


def test_password_round_trips_through_protection():
    encrypted = encrypt_password("s3cret-value")
    assert decrypt_password(encrypted) == "s3cret-value"

    if sys.platform == "win32":
        assert encrypted.startswith("dpapi:")
