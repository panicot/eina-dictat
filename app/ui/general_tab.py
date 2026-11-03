"""Pestanya de configuració general."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.model_catalog import is_installed, models_for_language, resolve
from app.ui.icons import icon
from app.ui.theme import theme_manager
from app.ui.widgets import (
    Card,
    CheckBox,
    ComboBox,
    Divider,
    HotkeyDialog,
    KeycapButton,
    MicTestDialog,
    SectionLabel,
    SegmentedControl,
)

LANGUAGES = (("ca", "Català"), ("es", "Castellà"), ("en", "Anglès"))


def list_input_devices() -> list[tuple[str, str]]:
    """Retorna (etiqueta, valor) per als micròfons disponibles."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception:  # noqa: BLE001
        return []
    result: list[tuple[str, str]] = []
    seen: dict[str, int] = {}
    for info in devices:
        if int(info.get("max_input_channels", 0)) <= 0:
            continue
        name = str(info.get("name", "Micròfon")).strip()
        api_name = ""
        try:
            api_name = str(hostapis[int(info["hostapi"])]["name"])
        except Exception:  # noqa: BLE001
            pass
        label = f"{name} · {api_name}" if api_name else name
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            label = f"{label} ({seen[name]})"
        result.append((label, name))
    return result


class GeneralTab(QWidget):
    changed = Signal()
    manage_models_requested = Signal()
    language_selected = Signal(str)

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._loading = False
        self._audio_busy = False
        self._model_combos: dict[str, ComboBox] = {}
        self._model_status: dict[str, QLabel] = {}
        self._device_items: list[tuple[str, str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll = scroll
        content = QWidget()
        self.content = QVBoxLayout(content)
        self.content.setContentsMargins(28, 16, 28, 10)
        self.content.setSpacing(12)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._build_inputs()
        self._build_models()

        self.advanced_toggle = QPushButton("Avançat ▾")
        self.advanced_toggle.setObjectName("link")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setCursor(Qt.PointingHandCursor)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.content.addWidget(self.advanced_toggle, 0, Qt.AlignLeft)
        self._build_advanced()
        self.content.addStretch(1)

        theme_manager.changed.connect(self._refresh_icons)
        self._refresh_icons()
        self.bind(cfg)

    # ------------------------------------------------------------------ build

    def _build_inputs(self) -> None:
        self.content.addWidget(SectionLabel("Dictat"))
        card = Card(margins=(20, 16, 20, 16))

        top = QHBoxLayout()
        top.setSpacing(12)
        label_box = QVBoxLayout()
        label_box.setSpacing(2)
        title = QLabel("Tecla per dictar")
        title.setObjectName("value")
        hint = QLabel("Prem la tecla o la combinació que vulguis fer servir.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        label_box.addWidget(title)
        label_box.addWidget(hint)
        self.keycap = KeycapButton()
        self.keycap.clicked.connect(lambda: self._capture_hotkey(self.keycap, "hotkey"))
        top.addLayout(label_box, 1)
        top.addWidget(self.keycap, 0, Qt.AlignTop)
        card.body.addLayout(top)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        mode_label = QLabel("Mode")
        mode_label.setObjectName("muted")
        self.mode_segment = SegmentedControl(
            [("Prémer", None), ("Mantenir", None)], object_name="segmented"
        )
        self.mode_segment.changed.connect(self._mode_changed)
        self.mode_hint = QLabel("Prémer per començar i tornar a prémer per aturar.")
        self.mode_hint.setObjectName("hint")
        self.mode_hint.setWordWrap(True)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode_segment)
        mode_row.addWidget(self.mode_hint, 1)
        card.body.addLayout(mode_row)

        card.body.addWidget(Divider())

        mic_row = QHBoxLayout()
        mic_row.setSpacing(10)
        mic_label = QLabel("Micròfon")
        mic_label.setObjectName("muted")
        self.device_combo = ComboBox()
        self.device_combo.setMinimumWidth(240)
        self.device_combo.activated.connect(self._device_changed)
        self.refresh_button = QToolButton()
        self.refresh_button.setToolTip("Torna a detectar els micròfons")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.test_button = QPushButton("Prova el micròfon")
        self.test_button.setCursor(Qt.PointingHandCursor)
        self.test_button.clicked.connect(self._test_microphone)
        mic_row.addWidget(mic_label)
        mic_row.addWidget(self.device_combo, 1)
        mic_row.addWidget(self.refresh_button)
        mic_row.addWidget(self.test_button)
        card.body.addLayout(mic_row)

        self.device_error = QLabel("")
        self.device_error.setObjectName("warning")
        self.device_error.setWordWrap(True)
        self.device_error.hide()
        card.body.addWidget(self.device_error)

        lang_row = QHBoxLayout()
        lang_row.setSpacing(10)
        lang_label = QLabel("Idioma de dictat")
        lang_label.setObjectName("muted")
        self.lang_segment = SegmentedControl(
            [(l[1], l[0]) for l in LANGUAGES], object_name="segmented"
        )
        self.lang_segment.changed.connect(self._quick_language_changed)
        lang_row.addWidget(lang_label)
        lang_row.addWidget(self.lang_segment)
        lang_row.addStretch(1)
        card.body.addLayout(lang_row)

        self.content.addWidget(card)

    def _build_models(self) -> None:
        self.content.addWidget(SectionLabel("Model de transcripció"))
        card = Card(margins=(20, 16, 20, 16))
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        header.addSpacing(50)
        model_header = QLabel("MODEL")
        model_header.setObjectName("section")
        status_header = QLabel("ESTAT")
        status_header.setObjectName("section")
        status_header.setFixedWidth(140)
        header.addWidget(model_header, 1)
        header.addWidget(status_header)
        card.body.addLayout(header)

        for language, _label in LANGUAGES:
            row = QHBoxLayout()
            row.setSpacing(12)
            pill = QLabel(language.upper())
            pill.setObjectName("langPill")
            pill.setAlignment(Qt.AlignCenter)
            pill.setFixedWidth(38)
            combo = ComboBox()
            combo.setMinimumWidth(280)
            combo.activated.connect(
                lambda _idx, lang=language: self._model_changed(lang)
            )
            status = QLabel("")
            status.setMinimumWidth(140)
            row.addWidget(pill)
            row.addWidget(combo, 1)
            row.addWidget(status, 0)
            card.body.addLayout(row)
            self._model_combos[language] = combo
            self._model_status[language] = status

        link = QPushButton("Gestiona els models i descarrega'n de nous →")
        link.setObjectName("link")
        link.setCursor(Qt.PointingHandCursor)
        link.clicked.connect(self.manage_models_requested.emit)
        card.body.addWidget(link, 0, Qt.AlignLeft)
        self.content.addWidget(card)

    def _build_advanced(self) -> None:
        self.advanced_card = Card()
        self.advanced_card.hide()
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)

        lang_label = QLabel("Idioma inicial")
        lang_label.setObjectName("muted")
        self.initial_language_combo = ComboBox()
        for code, label in LANGUAGES:
            self.initial_language_combo.addItem(label, code)
        self.initial_language_combo.activated.connect(self._language_changed)
        grid.addWidget(lang_label, 0, 0)
        grid.addWidget(self.initial_language_combo, 0, 1)

        undo_label = QLabel("Tecla per desfer")
        undo_label.setObjectName("muted")
        self.undo_keycap = KeycapButton()
        self.undo_keycap.clicked.connect(
            lambda: self._capture_hotkey(self.undo_keycap, "undo_hotkey")
        )
        grid.addWidget(undo_label, 1, 0)
        grid.addWidget(self.undo_keycap, 1, 1, Qt.AlignLeft)

        insert_label = QLabel("Inserció del text")
        insert_label.setObjectName("muted")
        self.insert_combo = ComboBox()
        self.insert_combo.addItem("Automàtic (llarg → porta-retalls)", "auto")
        self.insert_combo.addItem("Escriure caràcter a caràcter", "type")
        self.insert_combo.addItem("Enganxar amb Ctrl+V", "paste")
        self.insert_combo.activated.connect(self._insert_changed)
        grid.addWidget(insert_label, 2, 0)
        grid.addWidget(self.insert_combo, 2, 1)

        self.beeps_check = CheckBox("Sons d'estat en començar i acabar")
        self.beeps_check.toggled.connect(self._beeps_changed)
        grid.addWidget(self.beeps_check, 3, 0, 1, 2)
        self.advanced_card.body.addLayout(grid)
        self.content.addWidget(self.advanced_card)

    # ------------------------------------------------------------------- data

    def bind(self, cfg: Config, current_language: str | None = None) -> None:
        self.cfg = cfg
        self._loading = True
        try:
            self.keycap.set_combo(cfg.hotkey)
            self.undo_keycap.set_combo(cfg.undo_hotkey)
            self.mode_segment.set_current(0 if cfg.mode == "toggle" else 1)
            self.mode_hint.setText(self._mode_text(cfg.mode))
            self.refresh_devices()
            index = self.initial_language_combo.findData(cfg.language)
            self.initial_language_combo.setCurrentIndex(max(0, index))
            
            # Busquem l'index de l'idioma actual (default a cfg.language)
            self.select_language(current_language or cfg.language)
            
            index = self.insert_combo.findData(cfg.insert_mode)
            self.insert_combo.setCurrentIndex(max(0, index))
            self.beeps_check.setChecked(bool(cfg.beeps))
            self.refresh_models()
        finally:
            self._loading = False

    @staticmethod
    def _mode_text(mode: str) -> str:
        if mode == "hold":
            return "Mantenir premuda mentre parles i deixar anar per transcriure."
        return "Prémer per començar i tornar a prémer per aturar."

    def refresh_devices(self) -> None:
        current = self.cfg.device or None
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("Micròfon per defecte", None)
        self._device_items = list_input_devices()
        for label, value in self._device_items:
            self.device_combo.addItem(label, value)
        found = False
        if current:
            for index in range(self.device_combo.count()):
                if self.device_combo.itemData(index) == current:
                    self.device_combo.setCurrentIndex(index)
                    found = True
                    break
        if current and not found:
            self.device_combo.addItem(f"{current} (no detectat)", current)
            self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
        self.device_combo.blockSignals(False)
        if not self._device_items:
            self.device_error.setText(
                "No s'ha detectat cap micròfon. Comprova la connexió i els permisos de Windows."
            )
            self.device_error.show()
        else:
            self.device_error.hide()
        self.set_audio_busy(self._audio_busy)

    def select_language(self, language: str) -> None:
        """Marca el botó d'idioma corresponent sense emetre senyals."""
        for index, (code, _label) in enumerate(LANGUAGES):
            if code == language:
                self.lang_segment.blockSignals(True)
                self.lang_segment.set_current(index)
                self.lang_segment.blockSignals(False)
                return

    def refresh_models(self) -> None:
        self._loading = True
        try:
            for language, _label in LANGUAGES:
                combo = self._model_combos[language]
                current = self.cfg.models.get(language, "base")
                current_repo = resolve(current)
                combo.blockSignals(True)
                combo.clear()
                seen: set[str] = set()
                for info in models_for_language(language, installed_only=True):
                    combo.addItem(info.name, info.repo_id)
                    seen.add(info.repo_id)
                if current_repo not in seen:
                    info = next(
                        (item for item in models_for_language(language, installed_only=False)
                         if item.repo_id == current_repo),
                        None,
                    )
                    name = info.name if info else current
                    combo.addItem(f"{name} (cal descarregar-lo)", current_repo)
                combo.addItem("Gestiona els models…", "__manage__")
                index = combo.findData(current_repo)
                combo.setCurrentIndex(index if index >= 0 else 0)
                combo.blockSignals(False)
                self._update_model_status(language)
        finally:
            self._loading = False

    def _update_model_status(self, language: str) -> None:
        repo = resolve(self.cfg.models.get(language, "base"))
        status = self._model_status[language]
        if is_installed(repo):
            status.setObjectName("success")
            status.setText("● A punt")
        else:
            status.setObjectName("warning")
            status.setText("● Cal descarregar-lo")
        style = status.style()
        style.unpolish(status)
        style.polish(status)

    # ---------------------------------------------------------------- actions

    def _capture_hotkey(self, button: KeycapButton, field: str) -> None:
        dialog = HotkeyDialog(button.combo(), self)
        if dialog.exec():
            combo = dialog.combo()
            button.set_combo(combo)
            setattr(self.cfg, field, combo)
            self._notify()

    def _mode_changed(self, index: int) -> None:
        if self._loading:
            return
        self.cfg.mode = "toggle" if index == 0 else "hold"
        self.mode_hint.setText(self._mode_text(self.cfg.mode))
        self._notify()

    def _device_changed(self, index: int) -> None:
        if self._loading:
            return
        value = self.device_combo.itemData(index)
        self.cfg.device = value or None
        self._notify()

    def _model_changed(self, language: str) -> None:
        if self._loading:
            return
        combo = self._model_combos[language]
        data = combo.currentData()
        if data == "__manage__":
            current = resolve(self.cfg.models.get(language, "base"))
            index = combo.findData(current)
            combo.blockSignals(True)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
            self.manage_models_requested.emit()
            return
        if data:
            self.cfg.models[language] = str(data)
            self._update_model_status(language)
            self._notify()

    def _quick_language_changed(self, index: int) -> None:
        if self._loading:
            return
        # El SegmentedControl retorna el valor del segon element de la tupla (el codi)
        code = self.lang_segment.items[index][1]
        self.language_selected.emit(code)

    def _language_changed(self, index: int) -> None:
        if self._loading:
            return
        self.cfg.language = self.initial_language_combo.itemData(index)
        self._notify()

    def _insert_changed(self, index: int) -> None:
        if self._loading:
            return
        self.cfg.insert_mode = self.insert_combo.itemData(index)
        self._notify()

    def _beeps_changed(self, checked: bool) -> None:
        if self._loading:
            return
        self.cfg.beeps = checked
        self._notify()

    def _test_microphone(self) -> None:
        dialog = MicTestDialog(self.cfg.device, self)
        dialog.exec()

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_toggle.setText("Avançat ▴" if checked else "Avançat ▾")
        self.advanced_card.setVisible(checked)
        if checked:
            QTimer.singleShot(
                0, lambda: self.scroll.ensureWidgetVisible(self.advanced_card, 0, 16)
            )

    def _notify(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _refresh_icons(self) -> None:
        colors = theme_manager.colors
        self.refresh_button.setIcon(icon("refresh", colors["muted"], 17))
        self.test_button.setIcon(icon("mic", colors["muted"], 16))

    def set_audio_busy(self, busy: bool) -> None:
        self._audio_busy = busy
        self.test_button.setEnabled(bool(self._device_items) and not busy)
        self.refresh_button.setEnabled(not busy)
