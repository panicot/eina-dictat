"""Finestra principal de configuració."""

from __future__ import annotations

import dataclasses
import shutil
from typing import Callable

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.model_catalog import is_installed, resolve
from app.ui.downloads import DownloadManager
from app.ui.general_tab import GeneralTab
from app.ui.icons import icon
from app.ui.models_tab import ModelsTab
from app.ui.theme import enable_dark_title_bar, theme_manager
from app.ui.widgets import (
    Divider,
    SegmentedControl,
    StatusChip,
    Toast,
    app_icon,
    logo_pixmap,
)


def clone_config(cfg: Config) -> Config:
    return dataclasses.replace(
        cfg,
        models=dict(cfg.models),
        initial_prompts=dict(cfg.initial_prompts),
        dictionary=dict(cfg.dictionary),
    )


class MainWindow(QMainWindow):
    manage_models_requested = Signal()
    exit_requested = Signal()
    theme_change_requested = Signal(str)
    dictation_language_selected = Signal(str)

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CustormWispeFlow — Configuració")
        self.setWindowIcon(app_icon())
        self._fit_to_screen()
        self.setMinimumSize(780, 620)
        self.working_cfg = clone_config(cfg)
        self.saved_cfg = clone_config(cfg)
        self._save_handler: Callable[[Config], tuple[bool, str]] | None = None
        self._allow_close = False
        self._state = "idle"
        self._status_text = "A punt"
        self._dictation_language = cfg.language

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_tabs())
        divider = Divider()
        root.addWidget(divider)
        self.stack = QStackedWidget()
        self.download_manager = DownloadManager(self)
        self.general_tab = GeneralTab(self.working_cfg, self)
        self.general_tab.bind(self.working_cfg, self._dictation_language)
        self.models_tab = ModelsTab(self.working_cfg, self.download_manager, self)
        self.stack.addWidget(self.general_tab)
        self.stack.addWidget(self.models_tab)
        root.addWidget(self.stack, 1)
        root.addWidget(self._build_footer())

        self.toast = Toast(self)
        self._connect()
        self._update_dirty()
        for sequence, slot in (
            ("Ctrl+1", lambda: self.set_tab(0)),
            ("Ctrl+2", lambda: self.set_tab(1)),
            ("Ctrl+S", self.save),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)
        QTimer.singleShot(0, self._apply_title_bar)

    # ------------------------------------------------------------------ build

    def _fit_to_screen(self) -> None:
        """Mida còmoda per defecte, retallada si la pantalla és petita."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(880, 740)
            return
        available = screen.availableGeometry()
        width = min(880, max(780, available.width() - 80))
        height = min(740, max(620, available.height() - 80))
        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 3,
        )

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 18, 24, 14)
        layout.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(38))
        logo.setFixedSize(38, 38)
        layout.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("CustormWispeFlow")
        title.setObjectName("appTitle")
        subtitle = QLabel("Dictat local · sense núvol")
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles, 1)
        self.status_chip = StatusChip()
        layout.addWidget(self.status_chip, 0, Qt.AlignVCenter)
        self.theme_button = QToolButton()
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.setToolTip("Canvia entre tema fosc i clar")
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button, 0, Qt.AlignVCenter)
        self._refresh_theme_button()
        return header

    def _build_tabs(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(28, 0, 28, 12)
        layout.setSpacing(10)
        self.tabs = SegmentedControl(
            [("General", "gear"), ("Models", "download")], object_name="tabBar"
        )
        self.tabs.set_current(0)
        layout.addWidget(self.tabs)
        layout.addStretch(1)
        hint = QLabel("Ctrl+1  ·  Ctrl+2")
        hint.setObjectName("caption")
        layout.addWidget(hint)
        return row

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(Divider())
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(28, 12, 24, 12)
        row_layout.setSpacing(10)
        self.footer_status = QLabel("Desat")
        self.footer_status.setObjectName("caption")
        row_layout.addWidget(self.footer_status, 1)
        self.restore_button = QPushButton("Restaura")
        self.restore_button.setObjectName("ghost")
        self.restore_button.setCursor(Qt.PointingHandCursor)
        self.restore_button.clicked.connect(self.restore)
        self.save_button = QPushButton("Desa els canvis")
        self.save_button.setObjectName("primary")
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self.save)
        row_layout.addWidget(self.restore_button)
        row_layout.addWidget(self.save_button)
        layout.addWidget(row)
        return footer

    def _connect(self) -> None:
        self.tabs.changed.connect(self._tab_changed)
        self.general_tab.changed.connect(self._update_dirty)
        self.general_tab.manage_models_requested.connect(lambda: self.set_tab(1))
        self.models_tab.assign_requested.connect(self._assign_model)
        self.models_tab.delete_requested.connect(self._delete_model)
        self.models_tab.notify.connect(self.show_toast)
        theme_manager.changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ state

    def set_state(self, state: str, language: str | None = None) -> None:
        self._state = state
        self.status_chip.set_state(state, language)
        busy = state in {"listening", "transcribing"}
        self.general_tab.set_audio_busy(busy)
        self.save_button.setEnabled(not busy and self._is_dirty())
        self.restore_button.setEnabled(not busy and self._is_dirty())
        if state == "idle" and self._status_text == "A punt":
            self._update_footer()

    def set_language(self, language: str) -> None:
        self.status_chip.set_language(language)
        self.set_dictation_language(language)

    def set_status(self, message: str) -> None:
        self._status_text = message
        if not self._is_dirty():
            self._update_footer()

    def current_status(self) -> str:
        return self._status_text

    def set_save_handler(self, handler: Callable[[Config], tuple[bool, str]]) -> None:
        self._save_handler = handler

    def mark_saved(self) -> None:
        # Es conserva el mateix objecte de treball: les pestanyes hi guarden
        # referència i, si el substituíssim, deixarien d'actualitzar-lo.
        self.saved_cfg = clone_config(self.working_cfg)
        self._status_text = "A punt"
        self._update_dirty()
        self.show_toast("Configuració desada", "info")

    def set_theme_state(self, name: str) -> None:
        self.working_cfg.theme = name
        self.saved_cfg.theme = name
        self._refresh_theme_button()
        self._apply_title_bar()

    # ------------------------------------------------------------------ dirty

    def _is_dirty(self) -> bool:
        return self.working_cfg != self.saved_cfg

    def _update_dirty(self) -> None:
        dirty = self._is_dirty()
        busy = self._state in {"listening", "transcribing"}
        self.save_button.setEnabled(dirty and not busy)
        self.restore_button.setEnabled(dirty and not busy)
        self._update_footer()

    def _update_footer(self) -> None:
        if self._is_dirty():
            self.footer_status.setObjectName("warning")
            self.footer_status.setText("● Canvis sense desar")
        else:
            ready = self._status_text.startswith("A punt")
            self.footer_status.setObjectName("success" if ready else "caption")
            self.footer_status.setText(self._status_text)
        style = self.footer_status.style()
        style.unpolish(self.footer_status)
        style.polish(self.footer_status)

    # ------------------------------------------------------------------ tabs

    def _tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.models_tab.refresh_all()

    def set_tab(self, index: int) -> None:
        self.tabs.set_current(index)
        self.stack.setCurrentIndex(index)

    # ----------------------------------------------------------------- models

    def _assign_model(self, language: str, repo_id: str) -> None:
        self.working_cfg.models[language] = repo_id
        self.general_tab.refresh_models()
        self.models_tab.set_config(self.working_cfg)
        self._update_dirty()
        self.show_toast(
            f"Model assignat a {_language_name(language)}. Desa els canvis per aplicar-lo.",
            "info",
        )

    def _delete_model(self, repo_id: str) -> None:
        from app.model_catalog import repo_dir

        folder = repo_dir(repo_id)
        try:
            if folder.exists():
                shutil.rmtree(folder)
        except OSError as exc:
            self.show_toast(f"No s'ha pogut eliminar: {exc}", "error")
            return
        self.models_tab.refresh_all()
        self.general_tab.refresh_models()
        self.show_toast("Model eliminat del disc", "info")

    # ------------------------------------------------------------------- save

    def save(self) -> None:
        for language in ("ca", "es", "en"):
            repo = resolve(self.working_cfg.models.get(language, "base"))
            if not is_installed(repo):
                self.show_toast(
                    f"Cal descarregar el model de {_language_name(language)} abans de desar.",
                    "warning",
                )
                self.set_tab(1)
                return
        if self._save_handler is None:
            return
        ok, message = self._save_handler(clone_config(self.working_cfg))
        if ok:
            self.mark_saved()
        else:
            self.show_toast(message, "error")

    def restore(self) -> None:
        self.working_cfg = clone_config(self.saved_cfg)
        self.general_tab.bind(self.working_cfg, self._dictation_language)
        self.models_tab.set_config(self.working_cfg)
        self._update_dirty()
        self.show_toast("Canvis descartats", "warning")

    def set_dictation_language(self, language: str) -> None:
        if self._dictation_language == language:
            return
        self._dictation_language = language
        self.general_tab.select_language(language)
        self.dictation_language_selected.emit(language)

    # ------------------------------------------------------------------ theme

    def _toggle_theme(self) -> None:
        new_name = "light" if theme_manager.name == "dark" else "dark"
        self.theme_change_requested.emit(new_name)

    def _on_theme_changed(self, _name: str) -> None:
        self._refresh_theme_button()
        self._apply_title_bar()
        self.toast.reposition()

    def _refresh_theme_button(self) -> None:
        colors = theme_manager.colors
        name = "sun" if theme_manager.name == "dark" else "moon"
        self.theme_button.setIcon(icon(name, colors["muted"], 18))

    def _apply_title_bar(self) -> None:
        enable_dark_title_bar(self, theme_manager.name == "dark")

    # ------------------------------------------------------------------ misc

    def show_toast(self, text: str, kind: str = "info") -> None:
        self.toast.show_message(text, kind)

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.exit_requested.emit()

    def force_close(self) -> None:
        self._allow_close = True
        self.close()

    def ask_exit(self) -> bool:
        """Mostra un diàleg de confirmació i torna True si l'usuari accepta."""
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            "Sortir",
            "Vols tancar CustormWispeFlow? El dictat es desactivarà.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._allow_close = True
            self.close()
            return True
        return False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast.reposition()


def _language_name(language: str) -> str:
    return {"ca": "Català", "es": "Castellà", "en": "Anglès"}.get(
        language, language.upper()
    )
