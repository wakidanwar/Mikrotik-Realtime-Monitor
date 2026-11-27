"""SwOS mode must load from config and show a port-status panel."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGridLayout

from app.collector import InterfaceReading, MonitorState
from app.config import AppConfig, InterfaceConfig, load_config
from app.ui import MonitorWindow, PortRow


def test_load_config_recognizes_swos_mode(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "router:\n"
        "  name: SW\n"
        "  host: 192.0.2.1\n"
        "  ros_version: SwOS\n"
        "  snmp:\n"
        "    enabled: true\n"
        "    community: public\n"
        "interfaces:\n"
        "  - name: ether1\n"
        "    label: UPLINK\n",
        encoding="utf-8",
    )

    config = load_config(str(path))

    assert config.router.device_type == "swos"
    assert config.router.ros_version == "SwOS"


def test_swos_dashboard_shows_ports_and_hides_router_cards():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    config.router.device_type = "swos"
    config.router.ros_version = "SwOS"
    config.interfaces = [
        InterfaceConfig(name="SFP4", label="UPLINK"),
        InterfaceConfig(name="Port1", label="LAN1"),
    ]
    window = MonitorWindow(config, MonitorState(config))

    assert set(window.port_rows) == {"SFP4", "Port1"}
    assert not hasattr(window, "users_value")
    assert not hasattr(window, "logs_list")


def test_swos_dashboard_uses_two_chart_columns_above_three_interfaces():
    app = QApplication.instance() or QApplication([])
    config = AppConfig()
    config.router.device_type = "swos"
    config.router.ros_version = "SwOS"
    config.interfaces = [
        InterfaceConfig(name=f"ether{i}", label=f"PORT{i}") for i in range(4)
    ]
    window = MonitorWindow(config, MonitorState(config))

    grid = window.findChild(QGridLayout)
    assert grid is not None
    assert grid.columnCount() == 2
    assert grid.count() == 4


def test_port_row_reports_link_and_speed():
    app = QApplication.instance() or QApplication([])
    row = PortRow(InterfaceConfig(name="ether1"))

    row.update(InterfaceReading(link_up=True, speed_mbps=1000))
    assert row.status_lbl.text() == "LINK UP"
    assert row.speed_lbl.text() == "1G"

    row.update(InterfaceReading(link_up=False))
    assert row.status_lbl.text() == "LINK DOWN"
    assert row.speed_lbl.text() == "--"
