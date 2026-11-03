"""Orquestra la finestra, la safata, l'overlay i el motor de dictat."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from app import settings_store
from app.config import Config, load
from app.model_catalog import display_name
from app.state import State
from app.ui.main_window import MainWindow
from app.ui.overlay import OverlayWindow
from app.ui.theme import apply_theme
from app.ui.tray import TrayController

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dictate import DictationApp  # noqa: E402


class Bridge(QObject):
    state = Signal(str)
    status = Signal(str)
    transcript = Signal(dict)
    error = Signal(str)
    language = Signal(str)
    undo = Signal(bool, str)
    quit_requested = Signal()


class DesktopApp(QObject):
    def __init__(self, qapp: QApplication, config: Config | None = None,
                 config_path: Path | None = None) -> None:
        super().__init__()
        self.qapp = qapp
        self.config_path = config_path
        self.cfg = config or load(config_path)
        apply_theme(qapp, self.cfg.theme)
        qapp.setQuitOnLastWindowClosed(False)

        self.bridge = Bridge()
        self.window = MainWindow(self.cfg)
        self.window.set_save_handler(self._save_config)
        self.overlay = OverlayWindow()
        self.tray = TrayController(self)
        self._tray_message_shown = False

        self.dictation = DictationApp(
            self.cfg,
            quiet=True,
            on_state=lambda state: self.bridge.state.emit(state.value),
            on_status=self.bridge.status.emit,
            on_transcript=self.bridge.transcript.emit,
            on_error=self.bridge.error.emit,
            on_language=self.bridge.language.emit,
            on_undo=self.bridge.undo.emit,
            on_quit=lambda: self.bridge.quit_requested.emit(),
        )

        self._connect()
        self.window.set_language(self.dictation.language)
        self.tray.set_language(self.dictation.language)
        self.window.show()
        QTimer.singleShot(0, self._start_engine)

    def _connect(self) -> None:
        self.bridge.state.connect(self._on_state)
        self.bridge.status.connect(self._on_status)
        self.bridge.transcript.connect(self._on_transcript)
        self.bridge.error.connect(self._on_error)
        self.bridge.language.connect(self._on_language)
        self.bridge.undo.connect(self._on_undo)
        self.bridge.quit_requested.connect(self.quit)

        self.window.theme_change_requested.connect(self._change_theme)
        self.window.exit_requested.connect(self._confirm_exit)

        self.tray.open_settings.connect(self._show_window)
        self.tray.toggle_dictation.connect(self.dictation.toggle)
        self.tray.undo_requested.connect(self.dictation.undo)
        self.tray.language_selected.connect(self.dictation.set_language)
        self.tray.theme_selected.connect(self._change_theme)
        self.tray.quit_requested.connect(self.quit)

        self.general_tab = self.window.general_tab
        self.general_tab.language_selected.connect(self.window.set_dictation_language)
        self.window.dictation_language_selected.connect(self.dictation.set_language)

        self.qapp.aboutToQuit.connect(self._shutdown)

    def _start_engine(self) -> None:
        self.window.set_status("Carregant model…")
        self.dictation.start_services()

    # ------------------------------------------------------------------ signals

    def _on_state(self, state: str) -> None:
        language = self.dictation.language
        self.window.set_state(state, language)
        self.overlay.set_state(state, language)
        self.tray.set_state(state, language)
        self.tray.set_language(language)
        if state == "idle" and self.window.current_status().startswith("Carregant"):
            self.window.set_status("A punt")

    def _on_status(self, message: str) -> None:
        if message.startswith("Model a punt: "):
            repo = message.split(": ", 1)[1]
            message = f"A punt · {display_name(repo)}"
        elif message.startswith("Carregant model"):
            message = "Carregant model…"
        self.window.set_status(message)
        if message.startswith("No s'ha pogut") and self.window.isVisible():
            self.window.show_toast(message, "error")

    def _on_transcript(self, payload: dict) -> None:
        chars = int(payload.get("chars", 0))
        self.overlay.show_transcript(chars)
        self.window.set_status(f"Text inserit · {chars} caràcters")
        QTimer.singleShot(
            2400,
            lambda: self.window.set_status("A punt")
            if self.dictation.state == State.IDLE else None,
        )

    def _on_error(self, message: str) -> None:
        self.overlay.show_error(message)
        self.window.set_status(message)
        if not self.window.isVisible():
            self.tray.show_message("CustormWispeFlow", message)

    def _on_language(self, language: str) -> None:
        self.window.set_language(language)
        self.tray.set_language(language)

    def _on_undo(self, ok: bool, message: str) -> None:
        kind = "info" if ok else "warning"
        self.overlay.show_message("Desfet" if ok else "No s'ha pogut desfer", kind, message)
        if self.window.isVisible():
            self.window.show_toast(message, "info" if ok else "warning")

    # ------------------------------------------------------------------- config

    def _save_config(self, cfg: Config) -> tuple[bool, str]:
        try:
            settings_store.save(cfg, self.config_path)
        except Exception as exc:  # noqa: BLE001
            return False, f"No s'ha pogut desar la configuració: {exc}"
        self.cfg = cfg
        self.dictation.apply_config(cfg)
        return True, ""

    def _change_theme(self, name: str) -> None:
        name = name if name in {"dark", "light"} else "dark"
        apply_theme(self.qapp, name)
        self.cfg.theme = name
        self.window.set_theme_state(name)
        self.tray.set_theme(name)
        try:
            settings_store.save(self.cfg, self.config_path)
        except Exception as exc:  # noqa: BLE001
            self.window.show_toast(f"No s'ha pogut desar el tema: {exc}", "error")

    # ------------------------------------------------------------------ window

    def _show_window(self) -> None:
        self.window.show_and_raise()

    def _hide_to_tray(self) -> None:
        if not self.tray.available:
            self.quit()
            return
        self.window.hide()
        if not self._tray_message_shown:
            self._tray_message_shown = True
            self.tray.show_message(
                "CustormWispeFlow",
                "Continua a la safata. Fes doble clic a la icona per obrir la configuració.",
            )

    def handle_connection(self, server: QLocalServer) -> None:
        socket = server.nextPendingConnection()
        if socket is None:
            return
        try:
            socket.readAll()
        except Exception:  # noqa: BLE001
            pass
        socket.disconnected.connect(socket.deleteLater)
        self._show_window()

    def quit(self) -> None:
        self._shutdown()
        self.overlay.close()
        self.tray.hide()
        self.window.force_close()
        self.qapp.quit()

    def _confirm_exit(self) -> None:
        if self.window.ask_exit():
            self.quit()

    def _shutdown(self) -> None:
        try:
            self.window.download_manager.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.dictation.shutdown()
        except Exception:  # noqa: BLE001
            pass
