"""Optional RouterOS API reader.

Used for values SNMP cannot provide reliably on RouterOS: the true
PPPoE + HotSpot session count, and exact RAM/CPU/uptime figures. The
module is optional: if ``librouteros`` is missing the monitor still runs
on SNMP alone.
"""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass, field

from app.config import ApiConfig
from app.metrics import count_ip_ranges, parse_routeros_uptime

log = logging.getLogger(__name__)

try:  # pragma: no cover - import guard
    from librouteros import connect as _connect
except ImportError:  # pragma: no cover
    _connect = None


@dataclass
class ApiReading:
    cpu_pct: float | None = None
    mem_pct: float | None = None
    uptime_s: float | None = None
    active_users: int | None = None
    pppoe_users: int | None = None
    hotspot_users: int | None = None
    dhcp_leases: int | None = None
    dhcp_pool_used: int | None = None
    dhcp_pool_size: int | None = None
    logs: list[dict[str, str]] = field(default_factory=list)


class RouterOsApi:
    """Persistent RouterOS API connection with lazy reconnect."""

    def __init__(self, host: str, config: ApiConfig):
        self.host = host
        self.config = config
        self._api = None

    @property
    def available(self) -> bool:
        return _connect is not None

    def _open(self):
        if _connect is None:
            raise RuntimeError("librouteros is not installed (pip install librouteros)")
        kwargs: dict = {
            "host": self.host,
            "username": self.config.username,
            "password": self.config.password,
            "port": self.config.port,
            "timeout": 3.0,
        }
        if self.config.use_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            kwargs["ssl_wrapper"] = lambda sock: context.wrap_socket(sock)
        return _connect(**kwargs)

    def close(self) -> None:
        if self._api is not None:
            try:
                self._api.close()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass
            finally:
                self._api = None

    def identity(self) -> str | None:
        """Return the router's system identity (best effort)."""
        if self._api is None:
            try:
                self._api = self._open()
            except Exception:  # noqa: BLE001
                return None
        try:
            row = next(iter(self._api.path("system", "identity")), None)
            if row:
                name = row.get("name")
                if name:
                    return str(name).strip()
        except Exception:  # noqa: BLE001
            pass
        return None

    def list_interfaces(self) -> list[str]:
        """Return interface names reported by RouterOS."""
        if self._api is None:
            try:
                self._api = self._open()
            except Exception:  # noqa: BLE001
                return []
        try:
            rows = list(self._api.path("interface"))
            names = [str(r.get("name")).strip() for r in rows if r.get("name")]
            return [n for n in names if n]
        except Exception:  # noqa: BLE001
            return []

    def poll(self) -> ApiReading:
        """Read one round of values. Raises on connection/protocol errors."""
        if self._api is None:
            self._api = self._open()
        reading = ApiReading()

        resource = next(iter(self._api.path("system", "resource")), None)
        if resource:
            cpu = resource.get("cpu-load")
            if cpu is not None:
                reading.cpu_pct = float(cpu)
            free = resource.get("free-memory")
            total = resource.get("total-memory")
            if isinstance(free, int) and isinstance(total, int) and total > 0:
                reading.mem_pct = (total - free) / total * 100.0
            reading.uptime_s = parse_routeros_uptime(resource.get("uptime"))

        sessions = 0
        found_menu = False
        for menu, field in ((("ppp", "active"), "pppoe_users"),
                            (("ip", "hotspot", "active"), "hotspot_users")):
            try:
                rows = list(self._api.path(*menu))
            except Exception:  # menu missing on this router / package disabled
                continue
            count = len(rows)
            setattr(reading, field, count)
            sessions += count
            found_menu = True
        if found_menu:
            reading.active_users = sessions

        try:
            leases = list(self._api.path("ip", "dhcp-server", "lease"))
            reading.dhcp_leases = sum(
                1 for row in leases
                if str(row.get("status", "") or "").lower() == "bound"
            )
        except Exception:  # DHCP server package disabled
            pass
        try:
            pools = list(self._api.path("ip", "pool"))
            size = sum(count_ip_ranges(str(row.get("ranges", "") or "")) for row in pools)
            used = list(self._api.path("ip", "pool", "used"))
            if size:
                reading.dhcp_pool_size = size
                reading.dhcp_pool_used = len(used)
        except Exception:  # pool menu unavailable
            pass

        try:
            log_entries = list(self._api.path("log"))
            reading.logs = [
                {
                    "time": str(item.get("time", "") or ""),
                    "topics": str(item.get("topics", "") or ""),
                    "message": str(item.get("message", "") or ""),
                }
                for item in log_entries[-20:]
                if item.get("message")
            ]
        except Exception:
            pass

        return reading
