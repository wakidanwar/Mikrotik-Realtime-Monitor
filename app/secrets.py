"""Windows DPAPI-based secret protection for router passwords.

Passwords are encrypted with the current user's DPAPI master key, so they
cannot be read by other users or moved to another machine. Falls back to
plain text on non-Windows platforms (dev/test) so the app keeps working.
"""
from __future__ import annotations

import base64
import ctypes
import os
import sys

_PREFIX = "dpapi:"
_MARKER = b"dpapi-v1"


def _is_windows() -> bool:
    return sys.platform == "win32"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def encrypt_password(plain: str) -> str:
    if not plain:
        return ""
    if not _is_windows():
        return plain
    try:
        crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        data = _MARKER + plain.encode("utf-8")
        in_blob = _DataBlob(len(data), (ctypes.c_byte * len(data))(*data))
        out_blob = _DataBlob()
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            return plain
        blob = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        kernel32.LocalFree(out_blob.pbData)
        return _PREFIX + base64.b64encode(blob).decode("ascii")
    except Exception:  # noqa: BLE001 - never crash on secret handling
        return plain


def decrypt_password(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        # Legacy plain-text value (migrated on next save).
        return stored
    if not _is_windows():
        return ""
    try:
        crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        raw = base64.b64decode(stored[len(_PREFIX):])
        in_blob = _DataBlob(len(raw), (ctypes.c_byte * len(raw))(*raw))
        out_blob = _DataBlob()
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            return ""
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        kernel32.LocalFree(out_blob.pbData)
        if not data.startswith(_MARKER):
            return ""
        return data[len(_MARKER):].decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""