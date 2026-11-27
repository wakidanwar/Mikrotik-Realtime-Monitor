"""Router profiles: save/load/switch between multiple MikroTik routers.

A profile is a plain JSON-serialisable bundle of connection settings and
the interfaces the user wants to monitor. Profiles live in ``routers.json``
next to the application so they persist between runs.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List

from app.paths import app_dir
from app.secrets import decrypt_password, encrypt_password

BASE_DIR = app_dir()
DEFAULT_ROUTERS_PATH = BASE_DIR / "routers.json"


def _normalize_ros_version(value: str) -> str:
    v = (value or "").strip().lower()
    if v in ("v6", "routeros v6", "6"):
        return "V6"
    if v in ("v7", "routeros v7", "7"):
        return "V7"
    if v in ("swos", "sw os", "switchos"):
        return "SwOS"
    return value.strip() or "V7"


@dataclass
class InterfaceChoice:
    name: str
    label: str = ""
    max_mbps: float = 0.0


@dataclass
class RouterProfile:
    name: str = ""
    host: str = ""
    login: str = "admin"
    password: str = ""
    community: str = "public"
    api_port: int = 8728
    api_use_ssl: bool = False
    ros_version: str = "V7"
    snmp_version: int = 2
    interfaces: List[InterfaceChoice] = field(default_factory=list)

    def display_name(self) -> str:
        return self.name.strip() or self.host.strip() or "Unnamed router"


class ProfileStore:
    def __init__(self, path: str = "routers.json"):
        if not path or not os.path.isabs(path):
            self.path = str((BASE_DIR / (path or "routers.json")).resolve())
        else:
            self.path = str(path)
        self.profiles: list[RouterProfile] = []
        self.active: str = ""
        self.load()

    # -- persistence -------------------------------------------------------
    def load(self) -> None:
        self.profiles = []
        self.active = ""
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.active = str(data.get("active", "") or "")
        legacy_password = False
        for item in data.get("profiles", []) or []:
            if not isinstance(item, dict):
                continue
            try:
                iface_raw = item.get("interfaces") or []
                ifaces = [
                    InterfaceChoice(
                        name=str(x.get("name", "")).strip(),
                        label=str(x.get("label", "") or "").strip(),
                        max_mbps=float(x.get("max_mbps", 0) or 0),
                    )
                    for x in iface_raw
                    if isinstance(x, dict) and str(x.get("name", "")).strip()
                ]
                profile = RouterProfile(
                    name=str(item.get("name", "") or "").strip(),
                    host=str(item.get("host", "") or "").strip(),
                    login=str(item.get("login", "admin") or "admin").strip(),
                    password=decrypt_password(str(item.get("password", "") or "")),
                    community=str(item.get("community", "public") or "public").strip(),
                    api_port=int(item.get("api_port", 8728) or 8728),
                    api_use_ssl=bool(item.get("api_use_ssl", False)),
                    ros_version=_normalize_ros_version(str(item.get("ros_version", "V7") or "V7")),
                    snmp_version=int(item.get("snmp_version", 2) or 2),
                    interfaces=ifaces,
                )
                if str(item.get("password", "") or "") and not str(item.get("password") or "").startswith("dpapi:"):
                    legacy_password = True
                self.profiles.append(profile)
            except (TypeError, ValueError):
                continue
        if legacy_password and sys.platform == "win32":
            try:
                self.save()  # rewrite legacy plain-text passwords with DPAPI
            except OSError:
                pass

    def save(self) -> None:
        payload = {"active": self.active, "profiles": []}
        for p in self.profiles:
            data = asdict(p)
            data["password"] = encrypt_password(p.password)
            payload["profiles"].append(data)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self.path)

    # -- accessors ---------------------------------------------------------
    def names(self) -> list[str]:
        return [p.display_name() for p in self.profiles]

    def get(self, name: str) -> RouterProfile | None:
        for p in self.profiles:
            if p.display_name() == name or p.name == name:
                return p
        return None

    def add_or_update(self, profile: RouterProfile) -> None:
        existing = self.get(profile.name) or self.get(profile.display_name())
        if existing is not None:
            idx = self.profiles.index(existing)
            self.profiles[idx] = profile
        else:
            self.profiles.append(profile)
        self.active = profile.display_name()
        self.save()

    def delete(self, name: str) -> bool:
        profile = self.get(name)
        if profile is None:
            return False
        self.profiles.remove(profile)
        if self.active == profile.display_name():
            self.active = self.profiles[0].display_name() if self.profiles else ""
        self.save()
        return True

    def active_profile(self) -> RouterProfile | None:
        if self.active:
            p = self.get(self.active)
            if p is not None:
                return p
        return self.profiles[0] if self.profiles else None

    @staticmethod
    def to_appconfig(profile: RouterProfile):
        from app.config import AppConfig, RouterConfig, SnmpConfig, ApiConfig, InterfaceConfig, PingConfig, PingTargetConfig, PollingConfig, OidsConfig
        interfaces = [
            InterfaceConfig(name=i.name, label=i.label or i.name, max_mbps=i.max_mbps)
            for i in profile.interfaces
        ]
        if not interfaces:
            interfaces = []
        return AppConfig(
            router=RouterConfig(
                name=profile.name or profile.host,
                host=profile.host,
                device_type="swos" if str(profile.ros_version).lower() == "swos" else "routeros",
                ros_version=profile.ros_version,
                snmp=SnmpConfig(
                    enabled=True,
                    version=profile.snmp_version,
                    community=profile.community,
                ),
                api=ApiConfig(
                    enabled=(profile.ros_version in ("V6", "V7")) and bool(profile.login),
                    port=profile.api_port,
                    username=profile.login,
                    password=profile.password,
                    use_ssl=profile.api_use_ssl,
                ),
            ),
            polling=PollingConfig(interval=1.0),
            interfaces=interfaces,
            ping=PingConfig(
                interval=1.0,
                timeout_ms=1000,
                window=60,
                targets=[
                    PingTargetConfig(name="Google DNS", host="8.8.8.8"),
                    PingTargetConfig(name="Google DNS 2", host="8.8.4.4"),
                    PingTargetConfig(name="Cloudflare", host="1.1.1.1"),
                    PingTargetConfig(name="Cloudflare 2", host="1.0.0.1"),
                ],
            ),
            oids=OidsConfig(),
        )
