"""Pestanya de models: catàleg, descàrregues i assignació per idioma."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.engine import MODELS_DIR
from app.model_catalog import (
    CATALOG,
    LANGUAGE_LABELS,
    ModelInfo,
    installed_models,
    installed_size_mb,
    installed_total_mb,
    is_installed,
    resolve,
)
from app.ui.downloads import DownloadManager
from app.ui.icons import icon
from app.ui.theme import theme_manager
from app.ui.widgets import Card, Divider, SegmentedControl


class ModelAvatar(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text[:1].upper(), parent)
        self.setObjectName("modelAvatar")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(42, 42)


class ModelCard(QFrame):
    download_requested = Signal(str)
    cancel_requested = Signal(str)
    assign_requested = Signal(str, str)
    delete_requested = Signal(str)
    details_toggled = Signal(bool)

    def __init__(self, info: ModelInfo, manager: DownloadManager,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info
        self.manager = manager
        self._assigned: list[str] = []
        self._details_visible = False
        self._error = ""
        self._state = manager.state(info.repo_id)
        self.setObjectName("recommendedCard" if info.recommended else "modelCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(9)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(ModelAvatar(info.name), 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.setSpacing(7)
        name = QLabel(info.name)
        name.setObjectName("cardTitle")
        name_row.addWidget(name)
        if info.recommended:
            name_row.addWidget(self._badge("Recomanat", "accent"))
        name_row.addWidget(self._badge(info.language_label, "neutral"))
        if "millor-qualitat" in info.tags:
            name_row.addWidget(self._badge("Més qualitat", "warning"))
        elif "rapid" in info.tags:
            name_row.addWidget(self._badge("Ràpid", "success"))
        name_row.addStretch(1)
        self.in_use_badge = self._badge("", "success")
        self.in_use_badge.hide()
        name_row.addWidget(self.in_use_badge)
        text_box.addLayout(name_row)
        desc = QLabel(info.description)
        desc.setObjectName("hint")
        desc.setWordWrap(True)
        text_box.addWidget(desc)
        meta = QLabel(
            f"{_size_label(info)}  ·  {info.speed}  ·  {info.quality}"
        )
        meta.setObjectName("caption")
        text_box.addWidget(meta)
        top.addLayout(text_box, 1)

        self.action_box = QVBoxLayout()
        self.action_box.setSpacing(6)
        self.download_button = QPushButton("Descarrega")
        self.download_button.setObjectName("primary")
        self.download_button.setCursor(Qt.PointingHandCursor)
        self.download_button.setIcon(icon("download", "#FFFFFF", 16))
        self.download_button.clicked.connect(
            lambda: self.download_requested.emit(self.info.repo_id)
        )
        self.more_button = QToolButton()
        self.more_button.setCursor(Qt.PointingHandCursor)
        self.more_button.setIcon(icon("more", theme_manager.colors["muted"], 18))
        self.more_button.setToolTip("Més accions")
        self.more_button.clicked.connect(self._show_menu)
        self.action_box.addWidget(self.download_button, 0, Qt.AlignRight)
        self.action_box.addWidget(self.more_button, 0, Qt.AlignRight)
        top.addLayout(self.action_box)
        root.addLayout(top)

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("downloadPanel")
        progress_layout = QHBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(12, 9, 10, 9)
        progress_layout.setSpacing(10)
        self.progress_label = QLabel("A la cua…")
        self.progress_label.setObjectName("caption")
        self.progress_label.setMinimumWidth(110)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.cancel_button = QToolButton()
        self.cancel_button.setIcon(icon("close", theme_manager.colors["muted"], 15))
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.setToolTip("Cancel·la la descàrrega")
        self.cancel_button.clicked.connect(
            lambda: self.cancel_requested.emit(self.info.repo_id)
        )
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress, 1)
        progress_layout.addWidget(self.cancel_button)
        self.progress_panel.hide()
        root.addWidget(self.progress_panel)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        root.addWidget(self.status_label)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.details_button = QPushButton("Detalls")
        self.details_button.setObjectName("link")
        self.details_button.setCursor(Qt.PointingHandCursor)
        self.details_button.clicked.connect(self._toggle_details)
        bottom.addWidget(self.details_button, 0, Qt.AlignLeft)
        self.installed_label = QLabel("")
        self.installed_label.setObjectName("caption")
        bottom.addWidget(self.installed_label)
        bottom.addStretch(1)
        self.details_arrow = QLabel("▾")
        self.details_arrow.setObjectName("caption")
        bottom.addWidget(self.details_arrow)
        root.addLayout(bottom)

        self.details = QWidget()
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(10)
        details_layout.addWidget(Divider())
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        rows = (
            ("Idiomes", ", ".join(LANGUAGE_LABELS.get(lang, lang) for lang in info.languages)),
            ("Mida", _size_label(info)),
            ("Velocitat", info.speed),
            ("Qualitat", info.quality),
            ("Llicència", info.license),
            ("Repositori", info.repo_id),
        )
        for row, (key, value) in enumerate(rows):
            key_label = QLabel(key)
            key_label.setObjectName("caption")
            value_label = QLabel(value)
            value_label.setObjectName("value")
            value_label.setWordWrap(True)
            grid.addWidget(key_label, row, 0)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        details_layout.addLayout(grid)
        actions = QHBoxLayout()
        source = QPushButton("Obre a Hugging Face")
        source.setObjectName("ghost")
        source.setCursor(Qt.PointingHandCursor)
        source.setIcon(icon("external", theme_manager.colors["muted"], 15))
        source.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(f"https://huggingface.co/{info.repo_id}")
            )
        )
        actions.addWidget(source)
        actions.addStretch(1)
        self.delete_button = QPushButton("Elimina el model")
        self.delete_button.setObjectName("danger")
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.setIcon(icon("trash", theme_manager.colors["danger"], 15))
        self.delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self.info.repo_id)
        )
        actions.addWidget(self.delete_button)
        details_layout.addLayout(actions)
        self.details.hide()
        root.addWidget(self.details)

        self._refresh_state()

    @staticmethod
    def _badge(text: str, variant: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("badge")
        label.setProperty("variant", variant)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Fes servir per a…").setEnabled(False)
        assigned = set(self._assigned)
        for language, label in (("ca", "Català"), ("es", "Castellà"), ("en", "Anglès")):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(language in assigned)
            action.triggered.connect(
                lambda _checked=False, lang=language: self.assign_requested.emit(
                    lang, self.info.repo_id
                )
            )
        menu.addSeparator()
        delete = menu.addAction("Elimina el model")
        delete.setEnabled(bool(self._assigned) is False)
        delete.triggered.connect(lambda: self.delete_requested.emit(self.info.repo_id))
        menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    def _toggle_details(self) -> None:
        self._details_visible = not self._details_visible
        self.details.setVisible(self._details_visible)
        self.details_button.setText("Amaga" if self._details_visible else "Detalls")
        self.details_arrow.setText("▴" if self._details_visible else "▾")
        self.details_toggled.emit(self._details_visible)

    def set_assigned(self, languages: list[str]) -> None:
        self._assigned = languages
        if languages:
            self.in_use_badge.setText(
                "En ús · " + ", ".join(lang.upper() for lang in languages)
            )
            self._set_badge_variant(self.in_use_badge, "accent")
            self.in_use_badge.show()
        else:
            self.in_use_badge.hide()
        self._refresh_state()

    @staticmethod
    def _set_badge_variant(label: QLabel, variant: str) -> None:
        label.setProperty("variant", variant)
        style = label.style()
        style.unpolish(label)
        style.polish(label)

    def set_state(self, state: str) -> None:
        self._state = state
        self._refresh_state()

    def set_progress(self, percent: int, speed: str, received: float, total: float) -> None:
        self.progress.setValue(percent)
        if percent >= 100:
            self.progress_label.setText("Instal·lat")
        else:
            self.progress_label.setText(f"{percent} % · {speed}")

    def set_error(self, message: str) -> None:
        self._error = message
        self.status_label.setObjectName("danger")
        self.status_label.setText(f"No s'ha pogut descarregar: {message}")
        self.status_label.show()
        style = self.status_label.style()
        style.unpolish(self.status_label)
        style.polish(self.status_label)

    def _refresh_state(self) -> None:
        installed = is_installed(self.info.repo_id)
        busy = self._state in {"queued", "downloading", "cancelling"}
        if installed:
            self.download_button.hide()
            self.more_button.show()
            self.progress_panel.hide()
            self.status_label.hide()
            size = installed_size_mb(self.info.repo_id)
            self.installed_label.setText(
                f"Instal·lat · {size} MB" if size else "Instal·lat"
            )
            if self._assigned:
                self._set_badge_variant(self.in_use_badge, "accent")
                self.in_use_badge.show()
            else:
                self.in_use_badge.setText("Instal·lat")
                self._set_badge_variant(self.in_use_badge, "success")
                self.in_use_badge.show()
            self.delete_button.setEnabled(not self._assigned)
        elif busy:
            self.download_button.hide()
            self.more_button.hide()
            self.progress_panel.show()
            self.installed_label.setText("")
            self.in_use_badge.hide()
            if self._state == "queued":
                self.progress_label.setText("A la cua…")
                self.progress.setValue(0)
            elif self._state == "cancelling":
                self.progress_label.setText("Cancel·lant…")
            self.delete_button.setEnabled(False)
        else:
            self.progress_panel.hide()
            self.more_button.hide()
            self.download_button.show()
            self.download_button.setText(
                "Torna-ho a provar" if self._state == "error" else "Descarrega"
            )
            self.in_use_badge.hide()
            self.installed_label.setText("")
            self.delete_button.setEnabled(False)
            if self._state != "error":
                self.status_label.hide()


class ModelsTab(QWidget):
    assign_requested = Signal(str, str)
    delete_requested = Signal(str)
    notify = Signal(str, str)
    models_changed = Signal()

    FILTERS = ("Tots", "Instal·lats", "Català", "Multilingüe")

    def __init__(self, cfg: Config, manager: DownloadManager,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.manager = manager
        self._cards: dict[str, ModelCard] = {}
        self._filter = 0
        self._search = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 20)
        outer.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("Models de transcripció")
        title.setObjectName("cardTitle")
        subtitle = QLabel("Descarrega models per transcriure localment.")
        subtitle.setObjectName("hint")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        storage_box = QVBoxLayout()
        storage_box.setSpacing(3)
        self.storage_label = QLabel("")
        self.storage_label.setObjectName("value")
        self.storage_label.setAlignment(Qt.AlignRight)
        open_folder = QPushButton("Obre la carpeta ↗")
        open_folder.setObjectName("link")
        open_folder.setCursor(Qt.PointingHandCursor)
        open_folder.clicked.connect(self._open_folder)
        storage_box.addWidget(self.storage_label, 0, Qt.AlignRight)
        storage_box.addWidget(open_folder, 0, Qt.AlignRight)
        header.addLayout(storage_box)
        outer.addLayout(header)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca un model…")
        self.search.addAction(icon("search", theme_manager.colors["muted"], 16), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._search_changed)
        self.filters = SegmentedControl(
            [(label, None) for label in self.FILTERS], object_name="segmented"
        )
        self.filters.set_current(0)
        self.filters.changed.connect(self._filter_changed)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.filters)
        outer.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        self.cards_layout = QVBoxLayout(container)
        self.cards_layout.setContentsMargins(0, 0, 6, 0)
        self.cards_layout.setSpacing(10)
        for info in CATALOG:
            card = ModelCard(info, manager)
            card.download_requested.connect(self.manager.enqueue)
            card.cancel_requested.connect(self.manager.cancel)
            card.assign_requested.connect(self.assign_requested.emit)
            card.delete_requested.connect(self._confirm_delete)
            card.details_toggled.connect(self._details_toggled)
            self._cards[info.repo_id] = card
            self.cards_layout.addWidget(card)
        self.empty = Card()
        self.empty.body.setAlignment(Qt.AlignCenter)
        empty_icon = QLabel()
        empty_icon.setPixmap(icon("mic", theme_manager.colors["muted"], 34).pixmap(QSize(34, 34)))
        empty_icon.setAlignment(Qt.AlignCenter)
        self.empty_title = QLabel("Encara no tens cap model")
        self.empty_title.setObjectName("cardTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_text = QLabel(
            "Descarrega el model recomanat per començar a dictar."
        )
        self.empty_text.setObjectName("hint")
        self.empty_text.setAlignment(Qt.AlignCenter)
        self.empty_text.setWordWrap(True)
        self.empty_button = QPushButton("Descarrega el recomanat")
        self.empty_button.setObjectName("primary")
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self._download_recommended)
        self.empty.body.addWidget(empty_icon)
        self.empty.body.addWidget(self.empty_title)
        self.empty.body.addWidget(self.empty_text)
        self.empty.body.addWidget(self.empty_button, 0, Qt.AlignCenter)
        self.cards_layout.addWidget(self.empty)
        self.cards_layout.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        manager.progress.connect(self._on_progress)
        manager.state_changed.connect(self._on_state)
        manager.finished.connect(self._on_finished)
        manager.failed.connect(self._on_failed)
        manager.cancelled.connect(self._on_cancelled)
        theme_manager.changed.connect(self._refresh_icons)

        self.set_config(cfg)
        self.refresh_filter()
        self._update_storage()

    # ---------------------------------------------------------------- helpers

    def _refresh_icons(self) -> None:
        self.search.actions()[0].setIcon(
            icon("search", theme_manager.colors["muted"], 16)
        )

    def set_config(self, cfg: Config) -> None:
        self.cfg = cfg
        assigned_by_repo: dict[str, list[str]] = {}
        for language in ("ca", "es", "en"):
            repo = resolve(cfg.models.get(language, "base"))
            assigned_by_repo.setdefault(repo, []).append(language)
        for repo, card in self._cards.items():
            card.set_assigned(assigned_by_repo.get(repo, []))
        self._update_storage()

    def _update_storage(self) -> None:
        models = installed_models()
        total = installed_total_mb()
        if models:
            size = f"{total / 1024:.1f} GB" if total >= 1024 else f"{total} MB"
            self.storage_label.setText(f"{len(models)} instal·lats · {size}")
        else:
            self.storage_label.setText("Cap model instal·lat")

    def refresh_filter(self) -> None:
        visible = 0
        for info in CATALOG:
            card = self._cards[info.repo_id]
            show = self._matches(info)
            card.setVisible(show)
            if show:
                visible += 1
        none_installed = not installed_models()
        self.empty.setVisible(visible == 0)
        if visible == 0:
            self.empty_title.setText("Cap model coincideix")
            self.empty_text.setText("Prova un altre filtre o neteja la cerca.")
            self.empty_button.setVisible(False)
        elif none_installed and self._filter in (0, 1) and not self._search:
            # El catàleg és visible però no hi ha res instal·lat: no cal tapar-lo.
            pass
        if not none_installed:
            self.empty_button.setVisible(False)
        self._update_storage()

    def _matches(self, info: ModelInfo) -> bool:
        if self._filter == 1 and not is_installed(info.repo_id):
            return False
        if self._filter == 2 and "ca" not in info.languages:
            return False
        if self._filter == 3 and not info.is_multilingual:
            return False
        if self._search:
            needle = self._search.casefold()
            haystack = " ".join(
                (info.name, info.description, info.repo_id, info.language_label)
            ).casefold()
            if needle not in haystack:
                return False
        return True

    def _search_changed(self, text: str) -> None:
        self._search = text.strip()
        self.refresh_filter()

    def _filter_changed(self, index: int) -> None:
        self._filter = index
        self.refresh_filter()

    def _details_toggled(self, _visible: bool) -> None:
        pass

    def refresh_all(self) -> None:
        for card in self._cards.values():
            card.set_state(self.manager.state(card.info.repo_id))
        self.set_config(self.cfg)
        self.refresh_filter()
        self._update_storage()

    # -------------------------------------------------------------- downloads

    def _download_recommended(self) -> None:
        for info in CATALOG:
            if info.recommended and not is_installed(info.repo_id):
                self.manager.enqueue(info.repo_id)
                return

    def _on_progress(self, repo_id: str, percent: int, speed: str,
                     received: float, total: float) -> None:
        card = self._cards.get(repo_id)
        if card:
            card.set_progress(percent, speed, received, total)

    def _on_state(self, repo_id: str, state: str) -> None:
        card = self._cards.get(repo_id)
        if card:
            card.set_state(state)
            if state == "installed":
                card.set_error("")
                self._update_storage()
                self.refresh_filter()

    def _on_finished(self, repo_id: str) -> None:
        self._update_storage()
        self.refresh_all()
        self.notify.emit("Model instal·lat. Ja el pots assignar a un idioma.", "info")

    def _on_failed(self, repo_id: str, message: str) -> None:
        card = self._cards.get(repo_id)
        if card:
            card.set_state("error")
            card.set_error(message.splitlines()[0][:180])
        self.notify.emit("No s'ha pogut descarregar el model.", "error")

    def _on_cancelled(self, repo_id: str) -> None:
        card = self._cards.get(repo_id)
        if card:
            card.set_state("idle")

    # ------------------------------------------------------------------ misc

    def _confirm_delete(self, repo_id: str) -> None:
        card = self._cards.get(repo_id)
        if card is None or not is_installed(repo_id):
            return
        if card._assigned:
            QMessageBox.warning(
                self,
                "Model en ús",
                "Aquest model està assignat a un idioma. Canvia'l per un altre "
                "abans d'eliminar-lo.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Eliminar el model",
            f"Vols eliminar {card.info.name}? Alliberaràs "
            f"{installed_size_mb(repo_id)} MB.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.delete_requested.emit(repo_id)

    def _open_folder(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(MODELS_DIR)))


def _size_label(info: ModelInfo) -> str:
    return f"{info.size_mb} MB"
