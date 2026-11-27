"""Entry point for the MikroTik real-time desktop monitor."""
from __future__ import annotations

import argparse
import logging
import os
import sys

from PySide6.QtWidgets import QApplication

from app.collector import MonitorState
from app.config import AppConfig, ConfigError, InterfaceConfig, load_config
from app.paths import app_dir, resource_path
from app.profiles import ProfileStore
from app.setup import SetupWindow
from app.ui import MonitorWindow


def _default_config() -> AppConfig:
    cfg = AppConfig()
    cfg.router.name = "Demo router"
    cfg.router.host = "192.168.88.1"
    cfg.interfaces = [
        InterfaceConfig(name="sfp-sfpplus1", label="UPLINK", max_mbps=1000),
        InterfaceConfig(name="ether3", label="LAN", max_mbps=1000),
    ]
    return cfg


def _install_controllers(app: QApplication, store: ProfileStore):
    """Wire setup/settings/dashboard transitions shared by all launch modes."""
    controller = {"dashboard": None, "setup": None, "demo": False, "direct": False}

    def stop_dashboard():
        dashboard = controller["dashboard"]
        if dashboard is not None:
            try:
                dashboard.stop()
            except Exception:
                pass
            dashboard.close()
            controller["dashboard"] = None

    def apply_config(config: AppConfig) -> None:
        build_dashboard(config, demo=controller["demo"])

    def on_settings_applied(config: AppConfig) -> None:
        apply_config(config)

    def get_setup() -> SetupWindow:
        setup = controller["setup"]
        if setup is None:
            setup = SetupWindow(store, on_quit=app.quit)
            setup.connect_requested.connect(connect_profile)
            setup.settings_applied.connect(on_settings_applied)
            controller["setup"] = setup
        return setup

    def open_settings(config: AppConfig, readonly: bool) -> None:
        setup = get_setup()
        setup.set_settings_mode(config, readonly=readonly, tab="Alarm")
        setup.showMaximized()
        setup.raise_()
        setup.activateWindow()

    def show_setup():
        stop_dashboard()
        setup = get_setup()
        setup.set_normal_mode()
        setup._refresh_routers_table()
        setup.showMaximized()
        setup.raise_()
        setup.activateWindow()

    def build_dashboard(config: AppConfig, demo: bool = False) -> MonitorWindow:
        stop_dashboard()
        controller["demo"] = demo
        state = MonitorState(config)
        dashboard = MonitorWindow(config, state)
        dashboard.setup_requested.connect(show_setup)
        dashboard.settings_requested.connect(
            lambda: open_settings(dashboard.config, readonly=controller["direct"])
        )
        dashboard.config_applied.connect(apply_config)
        controller["dashboard"] = dashboard
        dashboard.showMaximized()
        dashboard.start(demo=demo)
        return dashboard

    def connect_profile(profile):
        build_dashboard(ProfileStore.to_appconfig(profile), demo=False)

    controller["build_dashboard"] = build_dashboard
    controller["show_setup"] = show_setup
    controller["open_settings"] = open_settings
    return controller


def main() -> int:
    parser = argparse.ArgumentParser(description="MikroTik real-time desktop monitor")
    parser.add_argument("--config", default=None, help="path to config.yaml (skips setup screen)")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run with synthetic data (preview the UI without a router)",
    )
    parser.add_argument("--verbose", action="store_true", help="log collector details")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("MikroTik Real-Time Monitor")
    app.setQuitOnLastWindowClosed(False)

    base_dir = app_dir()
    from PySide6.QtGui import QIcon
    _icon_path = str(resource_path("assets/icon.png"))
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    store = ProfileStore(str(base_dir / "routers.json"))
    controller = _install_controllers(app, store)

    # Direct (non-interactive) modes.
    if args.demo:
        try:
            config = load_config(args.config) if args.config and os.path.exists(args.config) else _default_config()
        except ConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        controller["direct"] = True
        controller["build_dashboard"](config, demo=True)
        try:
            return app.exec()
        finally:
            controller["dashboard"].stop()
        return 0

    if args.config is not None:
        if not os.path.exists(args.config):
            print(f"Configuration error: configuration file not found: {args.config}", file=sys.stderr)
            return 2
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        controller["direct"] = True
        controller["build_dashboard"](config, demo=False)
        try:
            return app.exec()
        finally:
            if controller["dashboard"] is not None:
                controller["dashboard"].stop()
        return 0

    # Interactive setup flow.
    controller["show_setup"]()
    try:
        return app.exec()
    finally:
        if controller["dashboard"] is not None:
            try:
                controller["dashboard"].stop()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
