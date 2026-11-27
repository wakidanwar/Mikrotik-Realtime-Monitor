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

    # Direct (non-interactive) modes.
    if args.demo:
        try:
            config = load_config(args.config) if args.config and os.path.exists(args.config) else _default_config()
        except ConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        state = MonitorState(config)
        window = MonitorWindow(config, state)
        window.show()
        window.start(demo=True)
        try:
            return app.exec()
        finally:
            window.stop()
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
        state = MonitorState(config)
        window = MonitorWindow(config, state)
        window.show()
        window.start(demo=False)
        try:
            return app.exec()
        finally:
            window.stop()
        return 0

    # Interactive setup flow.
    controller = {"dashboard": None, "setup": None}

    def show_setup():
        if controller["dashboard"] is not None:
            try:
                controller["dashboard"].stop()
            except Exception:
                pass
            controller["dashboard"].close()
            controller["dashboard"] = None

        if controller["setup"] is not None:
            controller["setup"]._refresh_routers_table()
            controller["setup"].show()
            controller["setup"].raise_()
            controller["setup"].activateWindow()
        else:
            setup = SetupWindow(store, on_quit=app.quit)
            setup.connect_requested.connect(connect_profile)
            controller["setup"] = setup
            setup.show()

    def connect_profile(profile):
        if controller["setup"] is not None:
            controller["setup"].hide()
        config = ProfileStore.to_appconfig(profile)
        if config is None:
            from app.config import AppConfig
            config = AppConfig()
        state = MonitorState(config)
        dash = MonitorWindow(config, state)
        dash.setup_requested.connect(show_setup)
        controller["dashboard"] = dash
        dash.showMaximized()
        dash.start(demo=False)

    show_setup()
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
