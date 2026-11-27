"""Typed configuration loading for the monitor.

Secrets can be kept out of the file by using environment variables in
``config.yaml``::

    password: "${MIKROTIK_PASSWORD}"

Both ``${NAME}`` / ``$NAME`` and Windows-style ``%NAME%`` are expanded.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.paths import app_dir

DEFAULT_TEMPERATURE_OID = "1.3.6.1.4.1.14988.1.1.3.10.0"
DEFAULT_VOLTAGE_OID = "1.3.6.1.4.1.14988.1.1.3.8.0"


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


@dataclass
class SnmpConfig:
    enabled: bool = True
    version: int = 2
    community: str = "public"
    port: int = 161
    timeout: float = 1.0
    retries: int = 1


@dataclass
class ApiConfig:
    enabled: bool = False
    port: int = 8728
    username: str = ""
    password: str = ""
    use_ssl: bool = False
    interval: float = 2.0


@dataclass
class RouterConfig:
    name: str = "MikroTik Router"
    host: str = "192.168.88.1"
    device_type: str = "routeros"   # "routeros" or "swos"
    ros_version: str = "V7"        # "V6", "V7", or "SwOS"
    snmp: SnmpConfig = field(default_factory=SnmpConfig)
    api: ApiConfig = field(default_factory=ApiConfig)


@dataclass
class InterfaceConfig:
    name: str
    label: str = ""
    max_mbps: float = 0.0


@dataclass
class PingTargetConfig:
    name: str
    host: str


@dataclass
class PingConfig:
    interval: float = 1.0
    timeout_ms: int = 1000
    window: int = 60
    targets: list[PingTargetConfig] = field(default_factory=list)


@dataclass
class PollingConfig:
    interval: float = 1.0
    history_seconds: int = 120


@dataclass
class OidsConfig:
    temperature: str = DEFAULT_TEMPERATURE_OID
    voltage: str = DEFAULT_VOLTAGE_OID
    cpu: str = ""
    active_users: str = ""


@dataclass
class AppConfig:
    router: RouterConfig = field(default_factory=RouterConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    interfaces: list[InterfaceConfig] = field(default_factory=list)
    ping: PingConfig = field(default_factory=PingConfig)
    oids: OidsConfig = field(default_factory=OidsConfig)
    source_path: str = ""


_ENV_PATTERN = re.compile(r"\$\{(\w+)\}|\$(\w+)|%(\w+)%")


def _expand_env(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2) or match.group(3)
        return os.environ.get(name, "")

    return _ENV_PATTERN.sub(replace, text)


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"'{key}' must be a mapping, got {type(value).__name__}")
    return value


def _text(data: dict[str, Any], key: str, default: str, where: str) -> str:
    value = data.get(key, default)
    if value is None:
        return default
    return str(value).strip()


def _number(data: dict[str, Any], key: str, default: float, where: str,
            minimum: float, maximum: float) -> float:
    value = data.get(key, default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{where}.{key} must be a number, got {value!r}") from None
    if not minimum <= number <= maximum:
        raise ConfigError(f"{where}.{key} must be between {minimum} and {maximum}, got {number}")
    return number


def _integer(data: dict[str, Any], key: str, default: int, where: str,
             minimum: int, maximum: int) -> int:
    return int(_number(data, key, default, where, minimum, maximum))


def _flag(data: dict[str, Any], key: str, default: bool, where: str) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_interfaces(data: Any) -> list[InterfaceConfig]:
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ConfigError("'interfaces' must be a list")
    interfaces: list[InterfaceConfig] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ConfigError(f"interfaces[{index}] must be a mapping with a 'name' key")
        name = _text(item, "name", "", f"interfaces[{index}]")
        if not name:
            raise ConfigError(f"interfaces[{index}].name is required")
        interfaces.append(
            InterfaceConfig(
                name=name,
                label=_text(item, "label", "", f"interfaces[{index}]") or name,
                max_mbps=_number(item, "max_mbps", 0.0, f"interfaces[{index}]", 0, 1_000_000),
            )
        )
    if not interfaces:
        raise ConfigError("at least one interface must be configured under 'interfaces'")
    if len(interfaces) > 4:
        raise ConfigError("at most four interfaces are supported")
    return interfaces


def _parse_ping(data: dict[str, Any]) -> PingConfig:
    config = PingConfig(
        interval=_number(data, "interval", 1.0, "ping", 0.2, 60),
        timeout_ms=_integer(data, "timeout_ms", 1000, "ping", 100, 10_000),
        window=_integer(data, "window", 60, "ping", 5, 600),
    )
    raw_targets = data.get("targets") or []
    if not isinstance(raw_targets, list):
        raise ConfigError("'ping.targets' must be a list")
    for index, item in enumerate(raw_targets):
        if not isinstance(item, dict) or not item.get("host"):
            raise ConfigError(f"ping.targets[{index}] must have a 'host'")
        config.targets.append(
            PingTargetConfig(
                name=_text(item, "name", str(item["host"]), f"ping.targets[{index}]"),
                host=_text(item, "host", "", f"ping.targets[{index}]"),
            )
        )
    if len(config.targets) > 4:
        raise ConfigError("at most four ping targets are supported")
    return config


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Read and validate the YAML configuration file."""
    file_path = Path(path)
    if not file_path.is_file() and not file_path.is_absolute():
        candidate = app_dir() / path
        if candidate.is_file():
            file_path = candidate
    if not file_path.is_file():
        raise ConfigError(
            f"configuration file not found: {file_path}\n"
            "Copy config.example.yaml to config.yaml and edit it for your router."
        )

    try:
        raw = file_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"cannot read {file_path}: {exc}") from exc

    try:
        data = yaml.safe_load(_expand_env(raw)) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{file_path} must contain a YAML mapping at the top level")

    router_data = _section(data, "router")
    snmp_data = _section(router_data, "snmp")
    api_data = _section(router_data, "api")

    snmp = SnmpConfig(
        enabled=_flag(snmp_data, "enabled", True, "router.snmp"),
        version=_integer(snmp_data, "version", 2, "router.snmp", 1, 2),
        community=_text(snmp_data, "community", "public", "router.snmp"),
        port=_integer(snmp_data, "port", 161, "router.snmp", 1, 65535),
        timeout=_number(snmp_data, "timeout", 1.0, "router.snmp", 0.1, 30),
        retries=_integer(snmp_data, "retries", 1, "router.snmp", 0, 5),
    )
    api = ApiConfig(
        enabled=_flag(api_data, "enabled", False, "router.api"),
        port=_integer(api_data, "port", 8728, "router.api", 1, 65535),
        username=_text(api_data, "username", "admin", "router.api"),
        password=_text(api_data, "password", "", "router.api"),
        use_ssl=_flag(api_data, "use_ssl", False, "router.api"),
        interval=_number(api_data, "interval", 2.0, "router.api", 0.5, 60),
    )
    ros_version = _text(router_data, "ros_version", "V7", "router.ros_version") or "V7"
    device_type = _text(router_data, "device_type", "", "router.device_type").strip().lower()
    if ros_version.strip().lower() == "swos":
        device_type = "swos"
        ros_version = "SwOS"
    elif not device_type:
        device_type = "routeros"
    router = RouterConfig(
        name=_text(router_data, "name", "MikroTik", "router") or "MikroTik",
        host=_text(router_data, "host", "", "router"),
        snmp=snmp,
        api=api,
        device_type=device_type,
        ros_version=ros_version,
    )
    if not router.host:
        raise ConfigError("router.host is required (the router IP or DNS name)")
    if not snmp.enabled and not api.enabled:
        raise ConfigError("enable at least one of router.snmp or router.api")
    if snmp.enabled and not snmp.community:
        raise ConfigError("router.snmp.community is required when SNMP is enabled")

    polling_data = _section(data, "polling")
    polling = PollingConfig(
        interval=_number(polling_data, "interval", 1.0, "polling", 0.2, 60),
        history_seconds=_integer(polling_data, "history_seconds", 120, "polling", 10, 3600),
    )

    oids_data = _section(data, "oids")
    oids = OidsConfig(
        temperature=_text(oids_data, "temperature", DEFAULT_TEMPERATURE_OID, "oids"),
        voltage=_text(oids_data, "voltage", DEFAULT_VOLTAGE_OID, "oids"),
        cpu=_text(oids_data, "cpu", "", "oids"),
        active_users=_text(oids_data, "active_users", "", "oids"),
    )

    return AppConfig(
        router=router,
        polling=polling,
        interfaces=_parse_interfaces(data.get("interfaces")),
        ping=_parse_ping(_section(data, "ping")),
        oids=oids,
        source_path=str(file_path),
    )
