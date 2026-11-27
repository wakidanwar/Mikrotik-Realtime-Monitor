"""Background collectors plus the thread-safe state the UI renders.

Three worker types run in parallel and never touch Qt:

* ``SnmpCollector``  - one SNMP GET round per interval for health + counters
* ``ApiCollector``   - optional RouterOS API poll (sessions, exact RAM/CPU)
* ``PingWorker``     - one ICMP probe per target per interval

The GUI reads immutable ``Snapshot`` copies from ``MonitorState``.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from app.config import AppConfig, InterfaceConfig
from app.metrics import compute_bps
from app.ping import PingStats, PingWindow, PingWorker
from app.routeros_api import ApiReading, RouterOsApi
from app.snmp_client import SnmpClient, SnmpError

log = logging.getLogger(__name__)

# IF-MIB
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"
IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"
# HOST-RESOURCES-MIB (CPU load table / RAM storage)
HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"
HR_STORAGE_DESCR = "1.3.6.1.2.1.25.2.3.1.3"
HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"
# MIKROTIK-MIB
MT_CPU_LOAD_LEGACY = "1.3.6.1.4.1.14988.1.1.3.3.0"
MT_TEMPERATURE = "1.3.6.1.4.1.14988.1.1.3.10.0"
MT_VOLTAGE = "1.3.6.1.4.1.14988.1.1.3.8.0"
MT_HOTSPOT_USERS = "1.3.6.1.4.1.14988.1.1.5.2.0"
PPPOE_PREFIX = "<pppoe-"
PPPOE_REFRESH = 5.0

MEMORY_LABELS = ("ram", "main memory", "physical memory", "system memory")


@dataclass
class InterfaceReading:
    link_up: bool | None = None
    speed_mbps: float | None = None
    rx_bps: float | None = None
    tx_bps: float | None = None


@dataclass
class Snapshot:
    now: float
    status: str
    status_detail: str
    uptime_s: float | None
    cpu_pct: float | None
    mem_pct: float | None
    temp_c: float | None
    volt_v: float | None
    active_users: int | None
    active_users_source: str
    interfaces: dict[str, InterfaceReading]
    history: dict[str, list[tuple[float, float, float]]]
    interface_errors: dict[str, str]
    pings: list[PingStats]
    logs: list[dict[str, str]] = field(default_factory=list)
    pppoe_users: int | None = None
    hotspot_users: int | None = None
    dhcp_leases: int | None = None
    dhcp_pool_used: int | None = None
    dhcp_pool_size: int | None = None
    wall_now: float = 0.0


class MonitorState:
    """Latest values, rolling history and per-source health."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.lock = threading.RLock()
        history_len = max(10, int(config.polling.history_seconds / config.polling.interval) + 2)
        self._history: dict[str, deque[tuple[float, float, float]]] = {
            iface.name: deque(maxlen=history_len) for iface in config.interfaces
        }
        self._interfaces = {iface.name: InterfaceReading() for iface in config.interfaces}
        self._interface_errors = {iface.name: "" for iface in config.interfaces}
        self._counters: dict[str, tuple[float, int, int]] = {}

        self._uptime_s: float | None = None
        self._uptime_ts = 0.0
        self._cpu_pct: float | None = None
        self._mem_pct: float | None = None
        self._temp_c: float | None = None
        self._volt_v: float | None = None
        self._active_users: int | None = None
        self._users_source = ""
        self._pppoe_users: int | None = None
        self._hotspot_users: int | None = None
        self._dhcp_leases: int | None = None
        self._dhcp_pool_used: int | None = None
        self._dhcp_pool_size: int | None = None
        self._logs: list[dict[str, str]] = []

        self._ping_windows = {target.name: PingWindow(config.ping.window) for target in config.ping.targets}
        self._started = time.monotonic()
        self._rate_warmup_until = self._started + 3.0
        self._ok_ts: dict[str, float] = {}
        self._fail_counts: dict[str, int] = {}
        self._errors: dict[str, str] = {}

    # -- writers -----------------------------------------------------------
    def set_session_details(self, pppoe_users, hotspot_users, dhcp_leases,
                            dhcp_pool_used, dhcp_pool_size) -> None:
        with self.lock:
            for attr, value in (
                ("pppoe_users", pppoe_users), ("hotspot_users", hotspot_users),
                ("dhcp_leases", dhcp_leases), ("dhcp_pool_used", dhcp_pool_used),
                ("dhcp_pool_size", dhcp_pool_size),
            ):
                if value is not None:
                    setattr(self, f"_{attr}", value)

    def apply_snmp(self, *, ts: float, uptime_s: float | None, cpu_pct: float | None,
                   mem_pct: float | None, temp_c: float | None, volt_v: float | None,
                   active_users: int | None, counters: dict[str, tuple[int, int, int]],
                   oper: dict[str, bool | None], speeds: dict[str, float | None],
                   users_source: str = "SNMP") -> None:
        with self.lock:
            for name, (in_octets, out_octets, bits) in counters.items():
                reading = self._interfaces.get(name)
                if reading is None:
                    continue
                previous = self._counters.get(name)
                rx = tx = None
                warmup = ts < self._rate_warmup_until
                if previous is not None and not warmup:
                    elapsed = ts - previous[0]
                    rx = compute_bps(previous[1], in_octets, elapsed, bits)
                    tx = compute_bps(previous[2], out_octets, elapsed, bits)
                    # Guard against bogus counter jumps (e.g. bad baseline/wrap).
                    speed_mbps = speeds.get(name)
                    if speed_mbps and speed_mbps > 0:
                        cap = speed_mbps * 1_000_000 * 1.5
                        if rx is not None and rx > cap:
                            rx = None
                        if tx is not None and tx > cap:
                            tx = None
                self._counters[name] = (ts, in_octets, out_octets)
                reading.link_up = oper.get(name)
                reading.speed_mbps = speeds.get(name)
                if rx is not None and tx is not None:
                    reading.rx_bps = rx
                    reading.tx_bps = tx
                    self._history[name].append((ts, rx, tx))

            if uptime_s is not None:
                self._uptime_s = uptime_s
                self._uptime_ts = ts
            if cpu_pct is not None:
                self._cpu_pct = cpu_pct
            if mem_pct is not None:
                self._mem_pct = mem_pct
            if temp_c is not None:
                self._temp_c = temp_c
            if volt_v is not None:
                self._volt_v = volt_v
            if active_users is not None:
                self._active_users = active_users
                self._users_source = users_source
        self._mark_ok("snmp", ts)

    def apply_api(self, reading: ApiReading, ts: float) -> None:
        with self.lock:
            if reading.cpu_pct is not None:
                self._cpu_pct = reading.cpu_pct
            if reading.mem_pct is not None:
                self._mem_pct = reading.mem_pct
            if reading.uptime_s is not None:
                self._uptime_s = reading.uptime_s
                self._uptime_ts = ts
            if reading.active_users is not None:
                self._active_users = reading.active_users
                self._users_source = "RouterOS API"
            self.set_session_details(
                reading.pppoe_users, reading.hotspot_users, reading.dhcp_leases,
                reading.dhcp_pool_used, reading.dhcp_pool_size,
            )
            if reading.logs:
                self._logs = reading.logs
        self._mark_ok("api", ts)

    def set_logs(self, logs: list[dict[str, str]]) -> None:
        with self.lock:
            self._logs = logs

    def add_ping(self, name: str, rtt: float | None) -> None:
        with self.lock:
            window = self._ping_windows.get(name)
            if window is not None:
                window.add(time.monotonic(), rtt)

    def set_interface_error(self, name: str, message: str) -> None:
        with self.lock:
            if name in self._interface_errors:
                self._interface_errors[name] = message

    def reset_counters(self, names: set[str] | None = None) -> None:
        """Drop rate baselines so the next sample becomes a clean baseline.

        Used when interface mapping/OIDs change or after reconnect, to avoid
        bogus deltas (e.g. 32-bit wrap spikes) on the first post-reset sample.
        """
        with self.lock:
            if names is None:
                self._counters.clear()
            else:
                for name in names:
                    self._counters.pop(name, None)
            # Ignore rate samples briefly after a reset to avoid first-load spikes.
            self._rate_warmup_until = max(self._rate_warmup_until, time.monotonic() + 3.0)

    def _mark_ok(self, source: str, ts: float) -> None:
        with self.lock:
            self._ok_ts[source] = ts
            self._fail_counts[source] = 0
            self._errors.pop(source, None)

    def note_error(self, source: str, error: Exception | str) -> None:
        message = str(error) or type(error).__name__
        with self.lock:
            count = self._fail_counts.get(source, 0) + 1
            self._fail_counts[source] = count
            self._errors[source] = message
        if count == 1 or count % 30 == 0:
            log.warning("%s collector error (%d in a row): %s", source.upper(), count, message)

    # -- reader ------------------------------------------------------------
    def _status(self, now: float) -> tuple[str, str]:
        primary = "snmp" if self.config.router.snmp.enabled else "api"
        if primary not in self._ok_ts and self._ok_ts:
            primary = max(self._ok_ts, key=self._ok_ts.get)
        last = self._ok_ts.get(primary)
        failures = self._fail_counts.get(primary, 0)
        error = self._errors.get(primary, "")
        interval = self.config.polling.interval

        if last is None:
            if now - self._started < max(3.0, interval * 3):
                return "CONNECTING", f"connecting to {self.config.router.host}"
            return "OFFLINE", error or f"no response from {self.config.router.host}"

        age = now - last
        if failures == 0 and age <= max(3.0, interval * 2.5):
            status, detail = "ONLINE", ""
        elif failures < 3 and age <= max(10.0, interval * 6):
            status, detail = "DEGRADED", error or "intermittent data loss"
        else:
            status, detail = "OFFLINE", error or f"no response for {age:.0f}s"

        secondary = "api" if primary == "snmp" else "snmp"
        if status == "ONLINE" and secondary in self._errors:
            detail = f"{secondary.upper()}: {self._errors[secondary]}"
        return status, detail

    def snapshot(self, now: float | None = None) -> Snapshot:
        now = time.monotonic() if now is None else now
        with self.lock:
            status, detail = self._status(now)
            uptime = self._uptime_s
            if uptime is not None and 0 <= now - self._uptime_ts < 5.0:
                uptime += now - self._uptime_ts
            pings = [
                self._ping_windows[target.name].stats(target.name, target.host, now)
                for target in self.config.ping.targets
                if target.name in self._ping_windows
            ]
            return Snapshot(
                now=now,
                wall_now=time.time(),
                status=status,
                status_detail=detail,
                uptime_s=uptime,
                cpu_pct=self._cpu_pct,
                mem_pct=self._mem_pct,
                temp_c=self._temp_c,
                volt_v=self._volt_v,
                active_users=self._active_users,
                active_users_source=self._users_source,
                pppoe_users=self._pppoe_users,
                hotspot_users=self._hotspot_users,
                dhcp_leases=self._dhcp_leases,
                dhcp_pool_used=self._dhcp_pool_used,
                dhcp_pool_size=self._dhcp_pool_size,
                interfaces={
                    name: InterfaceReading(**vars(reading))
                    for name, reading in self._interfaces.items()
                },
                history={name: list(points) for name, points in self._history.items()},
                interface_errors=dict(self._interface_errors),
                pings=pings,
                logs=list(self._logs),
            )


# --- SNMP plan -----------------------------------------------------------------


@dataclass
class _InterfacePlan:
    config: InterfaceConfig
    index: str
    in_oid: str
    out_oid: str
    oper_oid: str
    speed_oid: str
    speed_mbps: float | None
    bits: int


@dataclass
class _Plan:
    interfaces: list[_InterfacePlan] = field(default_factory=list)
    missing: dict[str, str] = field(default_factory=dict)
    cpu_oids: list[str] = field(default_factory=list)
    memory: tuple[str, str] | None = None
    temperature_oid: str | None = None
    voltage_oid: str | None = None
    users_oid: str | None = None
    pppoe_users: bool = False


def _safe_get(client: SnmpClient, oid: str):
    try:
        return client.get([oid]).get(oid)
    except SnmpError:
        return None


def _safe_walk(client: SnmpClient, oid: str) -> dict[str, object]:
    try:
        return client.walk(oid)
    except SnmpError:
        return {}


def _scale_health(raw) -> float | None:
    """Temperature/Voltage use DISPLAY-HINT "d-1" (tenths) in MIKROTIK-MIB.

    A few RouterOS builds report whole units instead, so values below 100
    are taken as-is (a router is never 4.1 C or 2.4 V).
    """
    if not isinstance(raw, int) or raw < 0:
        return None
    return raw / 10.0 if raw >= 100 else float(raw)


class SnmpCollector(threading.Thread):
    def __init__(self, config: AppConfig, state: MonitorState, stop_event: threading.Event):
        super().__init__(name="snmp-collector", daemon=True)
        self.config = config
        self.state = state
        self.stop_event = stop_event
        self._pppoe_cached_count: int | None = None
        self._pppoe_cached_ts: float = 0.0

    def run(self) -> None:
        client: SnmpClient | None = None
        plan: _Plan | None = None
        next_resolve = 0.0
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                if client is None:
                    snmp = self.config.router.snmp
                    client = SnmpClient(
                        self.config.router.host,
                        community=snmp.community,
                        port=snmp.port,
                        timeout=snmp.timeout,
                        retries=snmp.retries,
                        version=snmp.version,
                    )
                if plan is None or started >= next_resolve:
                    old_keys = {
                        (p.config.name, p.in_oid, p.out_oid, p.bits)
                        for p in (plan.interfaces if plan else [])
                    }
                    plan = self._resolve(client)
                    new_keys = {
                        (p.config.name, p.in_oid, p.out_oid, p.bits)
                        for p in plan.interfaces
                    }
                    stale = {k[0] for k in old_keys if k not in new_keys} | {
                        k[0] for k in new_keys if k not in old_keys
                    }
                    if stale:
                        self.state.reset_counters(stale)
                    for iface in self.config.interfaces:
                        self.state.set_interface_error(iface.name, plan.missing.get(iface.name, ""))
                    if plan.missing or (not plan.pppoe_users and plan.users_oid is None):
                        next_resolve = started + 30.0
                    else:
                        next_resolve = started + 300.0
                values = self._poll(client, plan)
                self.state.apply_snmp(ts=time.monotonic(), **values)
            except Exception as exc:  # noqa: BLE001 - keep the thread alive
                log.warning("SNMP collector error: %s", exc)
                self.state.note_error("snmp", exc)
                if client is not None:
                    client.close()
                client = None
                plan = None
                # Drop baselines so reconnect/rescan does not produce a bogus delta.
                self.state.reset_counters()
                self.stop_event.wait(max(0.2, min(2.0, self.config.polling.interval)))
                continue

            elapsed = time.monotonic() - started
            self.stop_event.wait(max(0.05, self.config.polling.interval - elapsed))
        if client is not None:
            client.close()

    def _resolve(self, client: SnmpClient) -> _Plan:
        plan = _Plan()
        names = _safe_walk(client, IF_NAME)
        descriptions = _safe_walk(client, IF_DESCR)
        speeds = _safe_walk(client, IF_HIGH_SPEED)

        index_by_name: dict[str, str] = {}
        for table in (names, descriptions):
            for oid, value in table.items():
                if isinstance(value, str):
                    index_by_name.setdefault(value.strip().lower(), oid.rsplit(".", 1)[-1])

        for iface in self.config.interfaces:
            name = iface.name.strip()
            index = name if name.isdigit() else index_by_name.get(name.lower())
            if index is None:
                plan.missing[iface.name] = f"interface '{iface.name}' not found on router"
                continue
            hc_in = f"{IF_HC_IN_OCTETS}.{index}"
            if _safe_get(client, hc_in) is not None:
                in_oid, out_oid, bits = hc_in, f"{IF_HC_OUT_OCTETS}.{index}", 64
            else:
                in_oid, out_oid, bits = f"{IF_IN_OCTETS}.{index}", f"{IF_OUT_OCTETS}.{index}", 32
            raw_speed = speeds.get(f"{IF_HIGH_SPEED}.{index}")
            speed_mbps = float(raw_speed) if isinstance(raw_speed, int) and raw_speed > 0 else None
            plan.interfaces.append(
                _InterfacePlan(
                    config=iface,
                    index=index,
                    in_oid=in_oid,
                    out_oid=out_oid,
                    oper_oid=f"{IF_OPER_STATUS}.{index}",
                    speed_oid=f"{IF_HIGH_SPEED}.{index}",
                    speed_mbps=speed_mbps or (iface.max_mbps or None),
                    bits=bits,
                )
            )

        # CPU: vendor scalar first, otherwise average the hrProcessorLoad table.
        if self.config.oids.cpu:
            plan.cpu_oids = [self.config.oids.cpu]
        elif isinstance(_safe_get(client, MT_CPU_LOAD_LEGACY), int):
            plan.cpu_oids = [MT_CPU_LOAD_LEGACY]
        else:
            plan.cpu_oids = list(_safe_walk(client, HR_PROCESSOR_LOAD).keys())

        # RAM: the hrStorage row labelled RAM (or the largest storage row).
        storage = _safe_walk(client, HR_STORAGE_DESCR)
        memory_index = None
        for oid, value in storage.items():
            if isinstance(value, str) and value.strip().lower() in MEMORY_LABELS:
                memory_index = oid.rsplit(".", 1)[-1]
                break
        if memory_index is None:
            sizes = _safe_walk(client, HR_STORAGE_SIZE)
            if sizes:
                best = max(sizes.items(), key=lambda item: item[1] if isinstance(item[1], int) else 0)
                memory_index = best[0].rsplit(".", 1)[-1]
        if memory_index is not None:
            plan.memory = (f"{HR_STORAGE_USED}.{memory_index}", f"{HR_STORAGE_SIZE}.{memory_index}")

        if self.config.oids.temperature and _safe_get(client, self.config.oids.temperature) is not None:
            plan.temperature_oid = self.config.oids.temperature
        if self.config.oids.voltage and _safe_get(client, self.config.oids.voltage) is not None:
            plan.voltage_oid = self.config.oids.voltage
        if not self.config.router.api.enabled:
            candidate = self.config.oids.active_users or MT_HOTSPOT_USERS
            if _safe_get(client, candidate) is not None:
                plan.users_oid = candidate
        # PPPoE sessions are exposed as dynamic <pppoe-*> interfaces in IF-MIB.
        plan.pppoe_users = any(
            isinstance(v, str) and v.strip().lower().startswith(PPPOE_PREFIX)
            for v in list(names.values()) + list(descriptions.values())
        )
        return plan

    def _poll(self, client: SnmpClient, plan: _Plan) -> dict:
        oids = [SYS_UPTIME]
        oids.extend(plan.cpu_oids)
        if plan.memory:
            oids.extend(plan.memory)
        if plan.temperature_oid:
            oids.append(plan.temperature_oid)
        if plan.voltage_oid:
            oids.append(plan.voltage_oid)
        if plan.users_oid:
            oids.append(plan.users_oid)
        for iface in plan.interfaces:
            oids.extend([iface.in_oid, iface.out_oid, iface.oper_oid, iface.speed_oid])
        values = client.get(list(dict.fromkeys(oids)))

        raw_uptime = values.get(SYS_UPTIME)
        uptime_s = raw_uptime / 100.0 if isinstance(raw_uptime, int) else None

        loads = [values[oid] for oid in plan.cpu_oids if isinstance(values.get(oid), int)]
        cpu_pct = sum(loads) / len(loads) if loads else None

        mem_pct = None
        if plan.memory:
            used = values.get(plan.memory[0])
            size = values.get(plan.memory[1])
            if isinstance(used, int) and isinstance(size, int) and size > 0:
                mem_pct = used / size * 100.0

        temp_c = _scale_health(values.get(plan.temperature_oid)) if plan.temperature_oid else None
        volt_v = _scale_health(values.get(plan.voltage_oid)) if plan.voltage_oid else None
        users_source = "N/A"
        users = 0
        has_users = False
        # RouterOS API owns active_users when enabled. SNMP must not publish a
        # second count here, otherwise the two threads overwrite each other's
        # value and the widget keeps flipping between both source labels.
        if not self.config.router.api.enabled:
            if plan.users_oid:
                raw_users = values.get(plan.users_oid)
                if isinstance(raw_users, int):
                    users += raw_users
                    has_users = True
            if plan.pppoe_users:
                count = self._pppoe_count(client)
                if count is not None:
                    users += count
                    has_users = True
        if has_users:
            active_users = users
            users_source = "SNMP"
        else:
            active_users = None

        counters: dict[str, tuple[int, int, int]] = {}
        oper: dict[str, bool | None] = {}
        speeds: dict[str, float | None] = {}
        for iface in plan.interfaces:
            name = iface.config.name
            in_octets = values.get(iface.in_oid)
            out_octets = values.get(iface.out_oid)
            if isinstance(in_octets, int) and isinstance(out_octets, int):
                counters[name] = (in_octets, out_octets, iface.bits)
            raw_status = values.get(iface.oper_oid)
            oper[name] = (raw_status == 1) if isinstance(raw_status, int) else None
            raw_speed = values.get(iface.speed_oid)
            speeds[name] = (
                float(raw_speed) if isinstance(raw_speed, int) and raw_speed > 0 else iface.speed_mbps
            )

        return {
            "uptime_s": uptime_s,
            "cpu_pct": cpu_pct,
            "mem_pct": mem_pct,
            "temp_c": temp_c,
            "volt_v": volt_v,
            "active_users": active_users,
            "users_source": users_source,
            "counters": counters,
            "oper": oper,
            "speeds": speeds,
        }


    def _pppoe_count(self, client: SnmpClient) -> int | None:
        now = time.monotonic()
        if now - self._pppoe_cached_ts >= PPPOE_REFRESH or self._pppoe_cached_count is None:
            try:
                table = client.walk(IF_DESCR)
                self._pppoe_cached_count = sum(
                    1 for v in table.values()
                    if isinstance(v, str) and v.strip().lower().startswith(PPPOE_PREFIX)
                )
                self._pppoe_cached_ts = now
            except SnmpError:
                pass
        return self._pppoe_cached_count

class ApiCollector(threading.Thread):
    def __init__(self, config: AppConfig, state: MonitorState, stop_event: threading.Event):
        super().__init__(name="api-collector", daemon=True)
        self.config = config
        self.state = state
        self.stop_event = stop_event
        self.api = RouterOsApi(config.router.host, config.router.api)

    def run(self) -> None:
        interval = self.config.router.api.interval
        if not self.api.available:
            self.state.note_error("api", "librouteros is not installed")
            return
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                reading = self.api.poll()
                self.state.apply_api(reading, time.monotonic())
            except Exception as exc:  # noqa: BLE001 - reconnect on the next tick
                log.warning("API collector error: %s", exc)
                self.state.note_error("api", exc)
                self.api.close()
            elapsed = time.monotonic() - started
            self.stop_event.wait(max(0.1, interval - elapsed))
        self.api.close()


class DemoCollector(threading.Thread):
    """Synthetic feed for ``--demo`` (preview the UI without a router)."""

    def __init__(self, config: AppConfig, state: MonitorState, stop_event: threading.Event):
        super().__init__(name="demo-collector", daemon=True)
        self.config = config
        self.state = state
        self.stop_event = stop_event

    def run(self) -> None:
        start = time.monotonic()
        previous = start
        octets = {iface.name: [0, 0] for iface in self.config.interfaces}
        while not self.stop_event.is_set():
            now = time.monotonic()
            elapsed = now - start
            delta = max(0.05, now - previous)
            previous = now

            counters = {}
            for index, iface in enumerate(self.config.interfaces):
                down = 45e6 + 32e6 * math.sin(elapsed / 9 + index * 1.7) + 3e6 * math.sin(elapsed * 0.7)
                up = 9e6 + 7e6 * math.sin(elapsed / 6 + index * 2.1) + 1e6 * math.sin(elapsed * 1.1)
                octets[iface.name][0] += int(max(0.2e6, down) / 8 * delta)
                octets[iface.name][1] += int(max(0.1e6, up) / 8 * delta)
                counters[iface.name] = (*octets[iface.name], 64)

            self.state.apply_snmp(
                ts=now,
                uptime_s=3 * 86_400 + 4 * 3_600 + elapsed,
                cpu_pct=19 + 13 * math.sin(elapsed / 11),
                mem_pct=54 + 6 * math.sin(elapsed / 23),
                temp_c=41.5 + 1.5 * math.sin(elapsed / 17),
                volt_v=23.8 + 0.2 * math.sin(elapsed / 19),
                active_users=int(42 + 6 * math.sin(elapsed / 31)),
                counters=counters,
                oper={iface.name: True for iface in self.config.interfaces},
                speeds={iface.name: (iface.max_mbps or 1000.0) for iface in self.config.interfaces},
                users_source="demo feed",
            )
            total = int(42 + 6 * math.sin(elapsed / 31))
            pppoe = int(total * 0.7)
            self.state.set_session_details(pppoe, total - pppoe, 170, 170, 200)
            demo_logs = [
                {"time": "09:12:04", "topics": "system,info", "message": "user admin logged in via winbox from 192.0.2.10"},
                {"time": "09:15:32", "topics": "interface,info", "message": "ether1 link up (speed 1G, full duplex)"},
                {"time": "09:20:11", "topics": "dhcp,info", "message": "dhcp1 assigned 192.0.2.45 to 00:11:22:33:44:55"},
                {"time": "09:33:48", "topics": "pppoe,info", "message": "pppoe-user01 connected, IP 10.10.1.20"},
                {"time": "09:45:10", "topics": "firewall,info", "message": "drop invalid: in:ether1 out:(unknown), proto TCP"},
                {"time": "10:02:15", "topics": "system,info", "message": "DNS cache flushed"},
                {"time": "10:14:22", "topics": "interface,info", "message": "sfp-sfpplus1 link up (speed 10G, full duplex)"},
            ]
            self.state.set_logs(demo_logs)
            for index, target in enumerate(self.config.ping.targets):
                if random.random() < 0.01:
                    rtt = None
                else:
                    rtt = 9.0 + index * 6 + 3.0 * math.sin(elapsed / 3 + index) + random.uniform(-1.0, 1.0)
                self.state.add_ping(target.name, rtt)
            self.stop_event.wait(self.config.polling.interval)


def build_collectors(config: AppConfig, state: MonitorState, stop_event: threading.Event,
                     demo: bool = False) -> list[threading.Thread]:
    if demo:
        return [DemoCollector(config, state, stop_event)]
    workers: list[threading.Thread] = []
    if config.router.snmp.enabled:
        workers.append(SnmpCollector(config, state, stop_event))
    if config.router.api.enabled:
        workers.append(ApiCollector(config, state, stop_event))
    for target in config.ping.targets:
        workers.append(PingWorker(target, config.ping, state.add_ping, stop_event))
    return workers
