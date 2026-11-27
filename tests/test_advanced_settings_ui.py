"""Advanced setup fields must feed the saved router profile."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from app.profiles import ProfileStore
from app.setup import SetupWindow


def test_setup_collects_advanced_fields_and_interface_capacity(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = SetupWindow(ProfileStore(str(tmp_path / "routers.json")))

    window.host_edit.setText("192.0.2.9")
    window.snmp_port_spin.setValue(1161)
    window.snmp_timeout_spin.setValue(2.5)
    window.snmp_retries_spin.setValue(3)
    window.api_interval_spin.setValue(5.0)
    window.polling_interval_spin.setValue(0.5)
    window.history_spin.setValue(300)
    window.ping_interval_spin.setValue(2.0)
    window.ping_timeout_spin.setValue(500)
    window.ping_window_spin.setValue(120)
    window.oid_temperature_edit.setText("1.2.3")
    window.oid_active_users_edit.setText("1.2.6")

    item = QListWidgetItem("ether1")
    item.setData(Qt.UserRole, {"name": "ether1", "label": "ether1", "max_mbps": 1000})
    window.selected_list.addItem(item)

    profile = window._collect_profile()

    assert profile.snmp_port == 1161
    assert profile.snmp_timeout == 2.5
    assert profile.api_interval == 5.0
    assert profile.polling_interval == 0.5
    assert profile.ping_timeout_ms == 500
    assert profile.oid_temperature == "1.2.3"
    assert profile.oid_active_users == "1.2.6"
    assert profile.interfaces[0].max_mbps == 1000

    window.selected_list.setCurrentRow(0)
    window.iface_max_spin.setValue(500)
    assert window._collect_profile().interfaces[0].max_mbps == 500
