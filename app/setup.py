"""Pre-connection setup screen: router profiles, identity fetch, interface scan."""
from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.paths import resource_path
from app.profiles import InterfaceChoice, ProfileStore, RouterProfile
from app.routeros_api import RouterOsApi
from app.config import ApiConfig
from app.ui import FramelessMixin, TitleBar, scaled_qss
import qtawesome as qta


class TaskWorker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.result.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class SetupWindow(FramelessMixin, QMainWindow):
    connect_requested = Signal(object)  # RouterProfile

    def __init__(self, store: ProfileStore, on_quit: Callable[[], None] | None = None):
        super().__init__()
        self.store = store
        self.on_quit = on_quit
        self._workers: list[TaskWorker] = []
        self.setWindowTitle("Login SNMP Mikrotik")
        self.resize(1080, 700)
        from PySide6.QtGui import QIcon
        _ip = str(resource_path("assets/icon.png"))
        if os.path.exists(_ip):
            self.setWindowIcon(QIcon(_ip))
        self.setup_frameless()
        self.setStyleSheet(scaled_qss())
        self._build_ui()
        self._on_device_mode_changed(self.ros_combo.currentText())
        self._refresh_routers_table()
        profile = self.store.active_profile()
        if profile is not None:
            self._load_profile(profile)

    # -- UI construction ---------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = TitleBar("MikroTik Device Manager", "Profile & SNMP Setup")
        root.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(10)
        root.addWidget(body, 1)

        # toolbar
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(14, 8, 14, 8)
        tb.setSpacing(10)

        tb_icon = QLabel()
        tb_icon.setPixmap(qta.icon("fa5s.network-wired", color="#38bdf8").pixmap(18, 18))
        tb.addWidget(tb_icon)

        title = QLabel("MikroTik Device Profiles")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        tb.addWidget(title)
        tb.addStretch(1)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("primaryBtn")
        self.btn_save = QPushButton("Save Profile")
        self.btn_new = QPushButton("New Profile")
        self.btn_delete = QPushButton("Delete")
        for b in (self.btn_connect, self.btn_save, self.btn_new, self.btn_delete):
            tb.addWidget(b)
        body_layout.addWidget(toolbar)

        # main split
        split = QHBoxLayout()
        split.setSpacing(10)
        body_layout.addLayout(split, 1)

        # left: connection form + interfaces
        left = QVBoxLayout()
        left.setSpacing(10)
        split.addLayout(left, 1)

        grp_conn = QGroupBox("Connection Settings")
        self.form = QFormLayout(grp_conn)
        self.form.setLabelAlignment(Qt.AlignRight)
        self.form.setSpacing(7)

        self.ros_combo = QComboBox()
        self.ros_combo.addItems(["RouterOS V7", "RouterOS V6", "SwOS"])
        self.ros_combo.setCurrentText("RouterOS V7")
        self.form.addRow("Device Mode:", self.ros_combo)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("192.168.88.1")
        self.form.addRow("IP Address:", self.host_edit)

        self.login_edit = QLineEdit()
        self.login_edit.setText("admin")
        self.form.addRow("Login:", self.login_edit)

        self.pw_widget = QWidget()
        pw_row = QHBoxLayout(self.pw_widget)
        pw_row.setContentsMargins(0, 0, 0, 0)
        pw_row.setSpacing(6)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        pw_row.addWidget(self.password_edit, 1)
        self.btn_toggle_pw = QPushButton("Show")
        self.btn_toggle_pw.setFixedWidth(60)
        pw_row.addWidget(self.btn_toggle_pw)
        self.form.addRow("Password:", self.pw_widget)

        self.community_edit = QLineEdit()
        self.community_edit.setText("public")
        self.form.addRow("SNMP Community:", self.community_edit)

        self.api_port_spin = QSpinBox()
        self.api_port_spin.setRange(1, 65535)
        self.api_port_spin.setValue(8728)
        self.form.addRow("API Port:", self.api_port_spin)

        ident_row = QHBoxLayout()
        ident_row.setSpacing(6)
        self.identity_edit = QLineEdit()
        ident_row.addWidget(self.identity_edit, 1)
        self.btn_fetch_id = QPushButton("Fetch")
        ident_row.addWidget(self.btn_fetch_id)
        self.form.addRow("Router Name (Identity):", ident_row)
        left.addWidget(grp_conn)

        grp_if = QGroupBox("Interfaces")
        il = QVBoxLayout(grp_if)
        il.setSpacing(8)

        # Move Scan Interfaces button inside Interfaces box
        scan_row = QHBoxLayout()
        scan_lbl = QLabel("Interface Discovery:")
        scan_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        scan_row.addWidget(scan_lbl)
        scan_row.addStretch(1)
        self.btn_scan = QPushButton("Scan Interfaces")
        self.btn_scan.setObjectName("primaryBtn")
        scan_row.addWidget(self.btn_scan)
        il.addLayout(scan_row)

        lists_row = QHBoxLayout()
        lists_row.setSpacing(8)
        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Discovered:"))
        self.discovered_table = QTableWidget(0, 2)
        self.discovered_table.setHorizontalHeaderLabels(["Name", "Speed / Type"])
        self.discovered_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.discovered_table.setSelectionMode(QTableWidget.SingleSelection)
        self.discovered_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.discovered_table.verticalHeader().setVisible(False)
        self.discovered_table.horizontalHeader().setStretchLastSection(True)
        self.discovered_table.setAlternatingRowColors(True)
        self.discovered_table.setColumnWidth(0, 200)
        left_col.addWidget(self.discovered_table, 1)
        self.btn_use = QPushButton("Use  →")
        left_col.addWidget(self.btn_use)
        lists_row.addLayout(left_col, 1)

        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("Monitored:"))
        self.selected_list = QListWidget()
        right_col.addWidget(self.selected_list, 1)
        self.btn_remove = QPushButton("Remove")
        right_col.addWidget(self.btn_remove)
        lists_row.addLayout(right_col, 1)
        il.addLayout(lists_row)
        left.addWidget(grp_if, 1)

        # right: saved routers
        right = QVBoxLayout()
        right.setSpacing(10)
        split.addLayout(right, 1)

        grp_routers = QGroupBox("Saved Routers")
        rl = QVBoxLayout(grp_routers)
        self.routers_table = QTableWidget(0, 5)
        self.routers_table.setHorizontalHeaderLabels(["Identity", "IP Address", "Mode", "SNMP", "Monitored Interfaces"])
        self.routers_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.routers_table.setSelectionMode(QTableWidget.SingleSelection)
        self.routers_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.routers_table.verticalHeader().setVisible(False)
        self.routers_table.horizontalHeader().setStretchLastSection(True)
        self.routers_table.setAlternatingRowColors(True)
        self.routers_table.setColumnWidth(0, 150)
        self.routers_table.setColumnWidth(1, 130)
        self.routers_table.setColumnWidth(2, 70)
        self.routers_table.setColumnWidth(3, 90)
        rl.addWidget(self.routers_table)
        right.addWidget(grp_routers, 1)

        # quick info card
        grp_info = QGroupBox("Selected Profile Summary")
        info_layout = QVBoxLayout(grp_info)
        self.quick_info = QLabel("No profile selected.")
        self.quick_info.setWordWrap(True)
        self.quick_info.setStyleSheet("font-size: 11px;")
        info_layout.addWidget(self.quick_info)
        right.addWidget(grp_info)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #ef4444;")
        body_layout.addWidget(self.status_label)

        # icons (qtawesome)
        self.btn_connect.setIcon(qta.icon("fa5s.play", color="#ffffff"))
        self.btn_save.setIcon(qta.icon("fa5s.save", color="#38bdf8"))
        self.btn_new.setIcon(qta.icon("fa5s.plus", color="#38bdf8"))
        self.btn_delete.setIcon(qta.icon("fa5s.trash-alt", color="#f87171"))
        self.btn_scan.setIcon(qta.icon("fa5s.search", color="#ffffff"))
        self.btn_fetch_id.setIcon(qta.icon("fa5s.cloud-download-alt", color="#38bdf8"))
        self.btn_use.setIcon(qta.icon("fa5s.arrow-right", color="#38bdf8"))
        self.btn_remove.setIcon(qta.icon("fa5s.times", color="#f87171"))

        # wiring
        self.routers_table.itemSelectionChanged.connect(self._on_router_selected)
        self.btn_new.clicked.connect(self._new_profile)
        self.btn_delete.clicked.connect(self._delete_profile)
        self.btn_fetch_id.clicked.connect(self._fetch_identity)
        self.btn_scan.clicked.connect(self._scan)
        self.btn_use.clicked.connect(self._use_selected)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_save.clicked.connect(self._save)
        self.btn_connect.clicked.connect(self._connect)
        self.btn_toggle_pw.clicked.connect(self._toggle_password)
        self.ros_combo.currentTextChanged.connect(self._on_device_mode_changed)

    def _on_device_mode_changed(self, mode: str):
        is_swos = (mode or "").strip().lower() == "swos"
        self.form.setRowVisible(self.login_edit, not is_swos)
        self.form.setRowVisible(self.pw_widget, not is_swos)
        self.form.setRowVisible(self.api_port_spin, not is_swos)

    # -- profile handling --------------------------------------------------
    def _refresh_routers_table(self):
        self.routers_table.setRowCount(0)
        for p in self.store.profiles:
            row = self.routers_table.rowCount()
            self.routers_table.insertRow(row)
            it0 = QTableWidgetItem(p.display_name())
            it1 = QTableWidgetItem(p.host)
            it2 = QTableWidgetItem(p.ros_version)
            it3 = QTableWidgetItem(p.community)
            it4 = QTableWidgetItem(", ".join(i.name for i in p.interfaces))
            for it in (it0, it1, it2, it3, it4):
                it.setToolTip(p.display_name())
            self.routers_table.setItem(row, 0, it0)
            self.routers_table.setItem(row, 1, it1)
            self.routers_table.setItem(row, 2, it2)
            self.routers_table.setItem(row, 3, it3)
            self.routers_table.setItem(row, 4, it4)
            # tooltip with full interface list on last col
            it4.setToolTip(", ".join(i.name for i in p.interfaces))
        if self.store.active:
            for r in range(self.routers_table.rowCount()):
                if self.routers_table.item(r, 0).text() == self.store.active:
                    self.routers_table.selectRow(r)
                    break
            prof = self.store.active_profile()
            if prof is not None:
                self._update_quick_info(prof)

    def _on_router_selected(self):
        row = self.routers_table.currentRow()
        if row < 0:
            return
        name = self.routers_table.item(row, 0).text()
        profile = self.store.get(name)
        if profile is not None:
            self._load_profile(profile)
            self._update_quick_info(profile)

    def _load_profile(self, p: RouterProfile):
        self.host_edit.setText(p.host)
        self.login_edit.setText(p.login)
        self.password_edit.setText(p.password)
        self.community_edit.setText(p.community)
        self.api_port_spin.setValue(p.api_port)
        mapping = {"V6": "RouterOS V6", "V7": "RouterOS V7", "SwOS": "SwOS"}
        self.ros_combo.setCurrentText(mapping.get(p.ros_version, "RouterOS V7"))
        self._on_device_mode_changed(self.ros_combo.currentText())
        self.identity_edit.setText(p.name)
        self.selected_list.clear()
        for iface in p.interfaces:
            self.selected_list.addItem(iface.name)
        self._update_quick_info(p)

    def _update_quick_info(self, p: RouterProfile):
        lines = [
            f"Identity: {p.display_name()}",
            f"IP: {p.host}",
            f"Mode: {p.ros_version}",
            f"SNMP: {p.community}",
            f"API Port: {p.api_port}",
            f"Monitored: {len(p.interfaces)} interface(s)",
        ]
        if p.interfaces:
            lines.append("  " + ", ".join(i.name for i in p.interfaces))
        self.quick_info.setText("\n".join(lines))

    def _collect_profile(self) -> RouterProfile:
        name = self.identity_edit.text().strip() or self.host_edit.text().strip()
        interfaces = []
        for i in range(self.selected_list.count()):
            iname = self.selected_list.item(i).text().strip()
            if iname:
                interfaces.append(InterfaceChoice(name=iname, label=iname))
        return RouterProfile(
            name=name,
            host=self.host_edit.text().strip(),
            login=self.login_edit.text().strip(),
            password=self.password_edit.text(),
            community=self.community_edit.text().strip() or "public",
            api_port=int(self.api_port_spin.value()),
            api_use_ssl=self.api_port_spin.value() == 8729,
            ros_version={"RouterOS V6": "V6", "RouterOS V7": "V7", "SwOS": "SwOS"}[self.ros_combo.currentText()],
            snmp_version=2,
            interfaces=interfaces,
        )

    def _new_profile(self):
        self.routers_table.clearSelection()
        self.host_edit.clear()
        self.login_edit.setText("admin")
        self.password_edit.clear()
        self.community_edit.setText("public")
        self.api_port_spin.setValue(8728)
        self.ros_combo.setCurrentText("RouterOS V7")
        self._on_device_mode_changed("RouterOS V7")
        self.identity_edit.clear()
        self.discovered_table.setRowCount(0)
        self.selected_list.clear()
        self.status_label.setText("")
        self.status_label.setStyleSheet("color: #EF4444;")

    def _delete_profile(self):
        row = self.routers_table.currentRow()
        if row < 0:
            return
        name = self.routers_table.item(row, 0).text()
        if QMessageBox.question(self, "Delete profile", f"Delete '{name}'?") != QMessageBox.Yes:
            return
        self.store.delete(name)
        self._refresh_routers_table()
        profile = self.store.active_profile()
        if profile is not None:
            self._load_profile(profile)

    def _toggle_password(self):
        if self.password_edit.echoMode() == QLineEdit.Password:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_pw.setText("Hide")
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.btn_toggle_pw.setText("Show")

    # -- network actions ---------------------------------------------------
    def _profile_from_form(self) -> RouterProfile:
        return self._collect_profile()

    def _fetch_identity(self):
        profile = self._profile_from_form()
        if not profile.host:
            self.status_label.setText("Enter an IP address first.")
            self.status_label.setStyleSheet("color: #EF4444;")
            return
        self.status_label.setText("Fetching identity...")
        self.status_label.setStyleSheet("color: #22C55E;")
        self.btn_fetch_id.setEnabled(False)

        def fn():
            try:
                from app.snmp_client import SnmpClient
                c = SnmpClient(profile.host, community=profile.community, timeout=2.0, retries=1, version=profile.snmp_version)
                try:
                    val = c.get(["1.3.6.1.2.1.1.5.0"]).get("1.3.6.1.2.1.1.5.0")
                    if isinstance(val, str) and val.strip():
                        return val.strip()
                finally:
                    c.close()
            except Exception:
                pass
            if profile.login and str(profile.ros_version).upper() in ("V6", "V7"):
                api = RouterOsApi(profile.host, ApiConfig(
                    enabled=True, port=profile.api_port, username=profile.login,
                    password=profile.password, use_ssl=profile.api_use_ssl))
                try:
                    name = api.identity()
                    if name:
                        return name
                finally:
                    api.close()
            raise RuntimeError("Could not fetch identity (SNMP and API both failed).")

        worker = TaskWorker(fn)
        worker.result.connect(self._on_identity_result)
        worker.error.connect(self._on_identity_error)
        worker.finished.connect(lambda: self.btn_fetch_id.setEnabled(True))
        self._workers.append(worker)
        worker.start()

    def _on_identity_result(self, value):
        self.identity_edit.setText(str(value))
        self.status_label.setText(f"Identity: {value}")
        self.status_label.setStyleSheet("color: #22C55E;")

    def _on_identity_error(self, msg):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #EF4444;")

    def _scan(self):
        profile = self._profile_from_form()
        if not profile.host:
            self.status_label.setText("Enter an IP address first.")
            self.status_label.setStyleSheet("color: #EF4444;")
            return
        self.status_label.setText("Scanning interfaces...")
        self.status_label.setStyleSheet("color: #22C55E;")
        self.btn_scan.setEnabled(False)
        self.discovered_table.setRowCount(0)

        def fn():
            result = []  # list of (name, speed_str)
            # SNMP: walk ifName/ifDescr + ifHighSpeed
            speed_map = {}
            try:
                from app.snmp_client import SnmpClient
                c = SnmpClient(profile.host, community=profile.community, timeout=2.0, retries=1, version=profile.snmp_version)
                try:
                    names_table = c.walk("1.3.6.1.2.1.31.1.1.1.1")
                    if not names_table:
                        names_table = c.walk("1.3.6.1.2.1.2.2.1.2")
                    # ifHighSpeed (Mbps)
                    try:
                        hs = c.walk("1.3.6.1.2.1.31.1.1.1.15")
                        for oid, val in hs.items():
                            idx = oid.rsplit(".", 1)[-1]
                            if isinstance(val, int) and val > 0:
                                speed_map[idx] = val
                    except Exception:
                        pass
                    # ifSpeed (bps) fallback
                    try:
                        sp = c.walk("1.3.6.1.2.1.2.2.1.5")
                        for oid, val in sp.items():
                            idx = oid.rsplit(".", 1)[-1]
                            if idx not in speed_map and isinstance(val, int) and val > 0:
                                speed_map[idx] = val // 1_000_000
                    except Exception:
                        pass
                    # map ifName oid -> index
                    for oid, val in names_table.items():
                        if isinstance(val, str) and val.strip():
                            idx = oid.rsplit(".", 1)[-1]
                            mbps = speed_map.get(idx, 0)
                            if mbps >= 1000:
                                speed_str = f"{mbps//1000}G"
                            elif mbps > 0:
                                speed_str = f"{mbps}M"
                            else:
                                speed_str = "-"
                            result.append((val.strip(), speed_str))
                finally:
                    c.close()
            except Exception:
                pass
            # API fallback
            if not result and profile.login and profile.ros_version in ("V6", "V7"):
                try:
                    api = RouterOsApi(profile.host, ApiConfig(
                        enabled=True, port=profile.api_port, username=profile.login,
                        password=profile.password, use_ssl=profile.api_use_ssl))
                    try:
                        names = api.list_interfaces()
                        for n in names:
                            result.append((n, "-"))
                    finally:
                        api.close()
                except Exception:
                    pass
            # dedupe
            seen = set()
            out = []
            for name, speed in result:
                if name and name not in seen:
                    seen.add(name)
                    out.append((name, speed))
            if not out:
                raise RuntimeError("No interfaces found (SNMP and API both failed).")
            return out

        worker = TaskWorker(fn)
        worker.result.connect(self._on_scan_result)
        worker.error.connect(self._on_scan_error)
        worker.finished.connect(lambda: self.btn_scan.setEnabled(True))
        self._workers.append(worker)
        worker.start()

    def _on_scan_result(self, items):
        self.discovered_table.setRowCount(0)
        for name, speed in items:
            row = self.discovered_table.rowCount()
            self.discovered_table.insertRow(row)
            self.discovered_table.setItem(row, 0, QTableWidgetItem(name))
            self.discovered_table.setItem(row, 1, QTableWidgetItem(speed))
        self.status_label.setText(f"Found {len(items)} interfaces.")
        self.status_label.setStyleSheet("color: #22C55E;")

    def _on_scan_error(self, msg):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #EF4444;")

    def _use_selected(self):
        r = self.discovered_table.currentRow()
        if r < 0 and self.discovered_table.rowCount() > 0:
            r = 0
        if r >= 0:
            self._add_monitored(self.discovered_table.item(r, 0).text())
            return
        for it in self.discovered_table.selectedItems():
            if it.column() == 0:
                self._add_monitored(it.text())

    def _add_monitored(self, name):
        name = name.strip()
        if not name:
            return
        existing = {self.selected_list.item(i).text() for i in range(self.selected_list.count())}
        if name not in existing:
            self.selected_list.addItem(name)

    def _remove_selected(self):
        for it in self.selected_list.selectedItems():
            self.selected_list.takeItem(self.selected_list.row(it))

    # -- save / connect ----------------------------------------------------
    def _save(self):
        profile = self._collect_profile()
        if not profile.host:
            self.status_label.setText("IP Address is required.")
            self.status_label.setStyleSheet("color: #EF4444;")
            return
        if not profile.name:
            profile.name = profile.host
        self.store.add_or_update(profile)
        self._refresh_routers_table()
        self.status_label.setText(f"Saved profile '{profile.display_name()}'.")
        self.status_label.setStyleSheet("color: #22C55E;")

    def _connect(self):
        profile = self._collect_profile()
        if not profile.host:
            self.status_label.setText("IP Address is required.")
            self.status_label.setStyleSheet("color: #EF4444;")
            return
        if not profile.name:
            profile.name = profile.host
        self.store.add_or_update(profile)
        self._refresh_routers_table()
        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("color: #22C55E;")
        self.connect_requested.emit(profile)

    def closeEvent(self, event):
        if self.on_quit is not None:
            self.on_quit()
        super().closeEvent(event)