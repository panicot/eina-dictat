#!/usr/bin/env python3
"""CustormWispeFlow - aplicació d'escriptori amb safata i overlay."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

if sys.stdout is None:  # pythonw no té consola
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import load
from app.instance import SingleInstance
from app.logs import get_logger, setup_logging
from app.ui.application import DesktopApp
from app.ui.widgets import app_icon

ROOT = Path(__file__).resolve().parent
SERVER_NAME = "CustormWispeFlow.Desktop"


def _excepthook(exc_type, exc, tb) -> None:  # noqa: ANN001
    get_logger().error("unhandled exception", exc_info=(exc_type, exc, tb))
    traceback.print_exception(exc_type, exc, tb)
    try:
        QMessageBox.critical(
            None,
            "CustormWispeFlow",
            f"S'ha produït un error inesperat:\n\n{exc}",
        )
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="CustormWispeFlow (interfície)")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    setup_logging(ROOT / "logs")
    app = QApplication(sys.argv)
    app.setApplicationName("CustormWispeFlow")
    app.setApplicationDisplayName("CustormWispeFlow")
    app.setOrganizationName("CustormWispeFlow")
    app.setWindowIcon(app_icon())
    sys.excepthook = _excepthook

    probe = QLocalSocket()
    probe.connectToServer(SERVER_NAME)
    if probe.waitForConnected(250):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(250)
        probe.disconnectFromServer()
        return 0

    instance = SingleInstance()
    if instance.already_running:
        QMessageBox.information(
            None,
            "CustormWispeFlow",
            "Ja hi ha una instància de CustormWispeFlow en marxa.\n\n"
            "Tanca la versió de consola o l'aplicació que ja s'està executant.",
        )
        instance.close()
        return 1

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        QMessageBox.critical(
            None,
            "CustormWispeFlow",
            "No s'ha pogut iniciar el canal de comunicació de l'aplicació.",
        )
        instance.close()
        return 1

    desktop = DesktopApp(app, load(args.config), args.config)
    server.newConnection.connect(lambda: desktop.handle_connection(server))
    app.setWindowIcon(app_icon())
    try:
        return app.exec()
    finally:
        server.close()
        instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
