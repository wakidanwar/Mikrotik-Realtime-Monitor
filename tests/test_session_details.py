"""PPPoE/HotSpot split and DHCP pool utilisation from the RouterOS API."""

from app.collector import MonitorState
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
