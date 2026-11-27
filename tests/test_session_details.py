"""PPPoE/HotSpot split and DHCP pool utilisation from the RouterOS API."""

import threading

from app.collector import MonitorState, SnmpCollector, SYS_UPTIME, _Plan
from app.config import ApiConfig, AppConfig
from app.metrics import count_ip_ranges
from app.routeros_api import ApiReading, RouterOsApi


class FakeApi:
    def __init__(self, rows):
        self._rows = rows

    def path(self, *parts):
        return list(self._rows.get(parts, []))


def test_count_ip_ranges_handles_ranges_and_single_addresses():
    assert count_ip_ranges("192.168.1.10-192.168.1.19") == 10
    assert count_ip_ranges("10.0.0.1-10.0.0.5,10.0.0.20") == 6
    assert count_ip_ranges("") == 0


def test_poll_splits_sessions_and_reads_dhcp_pool():
    api = RouterOsApi("192.0.2.1", ApiConfig())
    api._api = FakeApi({
        ("system", "resource"): [{"cpu-load": "12", "uptime": "1d00:00:00"}],
        ("ppp", "active"): [{"name": "u1"}, {"name": "u2"}],
        ("ip", "hotspot", "active"): [{"name": "h1"}],
        ("ip", "dhcp-server", "lease"): [
            {"status": "bound"},
            {"status": "bound"},
            {"status": "offered"},
        ],
        ("ip", "pool"): [{"ranges": "192.168.1.10-192.168.1.14"}],
        ("ip", "pool", "used"): [
            {"address": "192.168.1.10"},
            {"address": "192.168.1.11"},
        ],
        ("log",): [],
    })

    reading = api.poll()

    assert reading.pppoe_users == 2
    assert reading.hotspot_users == 1
    assert reading.active_users == 3
    assert reading.dhcp_leases == 2
    assert reading.dhcp_pool_size == 5
    assert reading.dhcp_pool_used == 2


def test_monitor_state_exposes_session_details_in_snapshot():
    state = MonitorState(AppConfig())
    state.apply_api(ApiReading(
        active_users=3,
        pppoe_users=2,
        hotspot_users=1,
        dhcp_leases=7,
        dhcp_pool_used=8,
        dhcp_pool_size=10,
    ), 1000.0)

    snapshot = state.snapshot(now=1000.0)

    assert snapshot.active_users == 3
    assert snapshot.pppoe_users == 2
    assert snapshot.hotspot_users == 1
    assert snapshot.dhcp_leases == 7
    assert snapshot.dhcp_pool_used == 8
    assert snapshot.dhcp_pool_size == 10


def test_session_details_setter_is_available_to_demo_feed():
    state = MonitorState(AppConfig())
    state.set_session_details(42, 18, 170, 170, 200)

    snapshot = state.snapshot(now=1000.0)

    assert snapshot.pppoe_users == 42
    assert snapshot.hotspot_users == 18
    assert snapshot.dhcp_leases == 170
    assert snapshot.dhcp_pool_used == 170
    assert snapshot.dhcp_pool_size == 200


class FakeSnmpClient:
    def get(self, oids):
        return {SYS_UPTIME: 100}


def _snmp_poll_with_api(monkeypatch, api_enabled):
    config = AppConfig()
    config.router.api.enabled = api_enabled
    collector = SnmpCollector(config, MonitorState(config), threading.Event())
    monkeypatch.setattr(collector, "_pppoe_count", lambda client: 12)
    return collector._poll(FakeSnmpClient(), _Plan(pppoe_users=True))


def test_snmp_does_not_report_users_when_api_is_enabled(monkeypatch):
    values = _snmp_poll_with_api(monkeypatch, api_enabled=True)

    assert values["active_users"] is None


def test_snmp_still_counts_pppoe_when_api_is_disabled(monkeypatch):
    values = _snmp_poll_with_api(monkeypatch, api_enabled=False)

    assert values["active_users"] == 12
    assert values["users_source"] == "SNMP"


def test_active_users_source_does_not_flip_when_both_collectors_run(monkeypatch):
    config = AppConfig()
    config.router.api.enabled = True
    state = MonitorState(config)
    collector = SnmpCollector(config, state, threading.Event())
    monkeypatch.setattr(collector, "_pppoe_count", lambda client: 12)

    state.apply_api(ApiReading(active_users=12), 1001.0)
    state.apply_snmp(ts=1002.0, **collector._poll(FakeSnmpClient(), _Plan(pppoe_users=True)))

    assert state.snapshot(now=1002.0).active_users_source == "RouterOS API"
