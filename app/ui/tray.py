"""Icona de la safata del sistema i el seu menú."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.ui.theme import theme_manager
from app.ui.widgets import app_icon


class TrayController(QObject):
    open_settings = Signal()
    toggle_dictation = Signal()
    undo_requested = Signal()
    language_selected = Signal(str)
    theme_selected = Signal(str)
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("CustormWispeFlow — A punt")
        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        if self.available:
            self.tray.show()

    def _build_menu(self) -> None:
        open_action = QAction("Obre la configuració", self.menu)
        open_action.triggered.connect(self.open_settings.emit)
        self.menu.addAction(open_action)
        self.menu.addSeparator()

        self.toggle_action = QAction("Comença a dictar", self.menu)
        self.toggle_action.triggered.connect(self.toggle_dictation.emit)
        self.menu.addAction(self.toggle_action)

        undo_action = QAction("Desfer l'última inserció", self.menu)
        undo_action.triggered.connect(self.undo_requested.emit)
        self.menu.addAction(undo_action)

        self.language_menu = self.menu.addMenu("Idioma")
        self._language_actions: dict[str, QAction] = {}
        for code, label in (("ca", "Català"), ("es", "Castellà"), ("en", "Anglès")):
            action = QAction(label, self.menu)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, lang=code: self.language_selected.emit(lang))
            self.language_menu.addAction(action)
            self._language_actions[code] = action
        self.set_language("ca")

        self.theme_menu = self.menu.addMenu("Tema")
        self._theme_actions: dict[str, QAction] = {}
        for code, label in (("dark", "Fosc"), ("light", "Clar")):
            action = QAction(label, self.menu)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, name=code: self.theme_selected.emit(name))
            self.theme_menu.addAction(action)
            self._theme_actions[code] = action
        self.set_theme(theme_manager.name)

        self.menu.addSeparator()
        quit_action = QAction("Sortir", self.menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.open_settings.emit()

    def set_state(self, state: str, language: str | None = None) -> None:
        texts = {
            "idle": "A punt",
            "listening": "Escoltant",
            "transcribing": "Transcrivint",
            "error": "Error",
            "paused": "En pausa",
        }
        label = texts.get(state, "A punt")
        if language:
            label = f"{label} · {language.upper()}"
        self.tray.setToolTip(f"CustormWispeFlow — {label}")
        if state == "listening":
            self.toggle_action.setText("Atura el dictat")
            self.toggle_action.setEnabled(True)
        elif state == "transcribing":
            self.toggle_action.setText("Transcrivint…")
            self.toggle_action.setEnabled(False)
        else:
            self.toggle_action.setText("Comença a dictar")
            self.toggle_action.setEnabled(True)

    def set_language(self, language: str) -> None:
        for code, action in self._language_actions.items():
            action.setChecked(code == language)

    def set_theme(self, name: str) -> None:
        for code, action in self._theme_actions.items():
            action.setChecked(code == name)

    def show_message(self, title: str, message: str) -> None:
        if self.available:
            self.tray.showMessage(title, message, app_icon(), 2600)

    def hide(self) -> None:
        self.tray.hide()
