"""Paleta, tipografia i full d'estil de la interfície."""

from __future__ import annotations

import sys
from string import Template

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0B0F14",
        "surface": "#121821",
        "surface2": "#18202B",
        "elevated": "#1B2432",
        "input": "#0F141C",
        "border": "#263244",
        "border_strong": "#34445C",
        "text": "#EDF2F8",
        "muted": "#8EA0B6",
        "accent": "#7B6CFF",
        "accent_hover": "#8F83FF",
        "accent_soft": "#252148",
        "success": "#42D6A0",
        "success_soft": "#14352B",
        "warning": "#F2B84B",
        "warning_soft": "#3A2E16",
        "danger": "#F06B6B",
        "danger_soft": "#3B1F24",
        "keycap": "#1E2633",
        "keycap_border": "#324158",
        "scroll": "#2A3546",
        "scroll_hover": "#3B4A61",
        "selection": "#3A3670",
        "overlay": "#151C27",
    },
    "light": {
        "bg": "#F4F6FB",
        "surface": "#FFFFFF",
        "surface2": "#EEF1F8",
        "elevated": "#FFFFFF",
        "input": "#F7F8FC",
        "border": "#DFE4EE",
        "border_strong": "#C8D0DF",
        "text": "#151A22",
        "muted": "#66758C",
        "accent": "#5B4BE0",
        "accent_hover": "#6C5CF0",
        "accent_soft": "#ECE9FF",
        "success": "#1F9D72",
        "success_soft": "#E2F6EE",
        "warning": "#B97A0A",
        "warning_soft": "#FFF2D8",
        "danger": "#C94A4A",
        "danger_soft": "#FDE8E8",
        "keycap": "#F1F3F9",
        "keycap_border": "#D4DAE7",
        "scroll": "#C9D0DD",
        "scroll_hover": "#AEB8CA",
        "selection": "#DDD8FF",
        "overlay": "#FFFFFF",
    },
}

FONT_FAMILY = '"Segoe UI Variable", "Segoe UI", sans-serif'
MONO_FAMILY = '"Cascadia Mono", "Cascadia Code", Consolas, monospace'

QSS_TEMPLATE = Template(
    """
* { outline: none; }
QWidget {
    color: $text;
    font-family: $font;
    font-size: 13.5px;
}
QMainWindow, QDialog { background: $bg; }
QFrame#card {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame#modelCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame#modelCard:hover { border-color: $border_strong; background: $surface2; }
QFrame#recommendedCard {
    background: $surface;
    border: 1px solid $accent;
    border-radius: 12px;
}
QFrame#segmented, QFrame#tabBar {
    background: $surface;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#statusChip {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame#divider { background: $border; border: none; }
QFrame#toast {
    background: $elevated;
    border: 1px solid $border_strong;
    border-radius: 10px;
}
QFrame#downloadPanel {
    background: $surface2;
    border: 1px solid $border;
    border-radius: 10px;
}
QLabel { background: transparent; }
QLabel#appTitle { font-size: 15px; font-weight: 600; }
QLabel#appSubtitle { font-size: 12px; color: $muted; }
QLabel#section {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    color: $muted;
}
QLabel#cardTitle { font-size: 15px; font-weight: 600; }
QLabel#muted { color: $muted; }
QLabel#hint { color: $muted; font-size: 12px; }
QLabel#caption { color: $muted; font-size: 12px; }
QLabel#value { font-size: 14px; font-weight: 500; }
QLabel#danger { color: $danger; font-size: 12px; }
QLabel#warning { color: $warning; font-size: 12px; }
QLabel#success { color: $success; font-size: 12px; }
QLabel#badge {
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
    background: $surface2;
    color: $muted;
}
QLabel#badge[variant="accent"] { background: $accent_soft; color: $accent; }
QLabel#badge[variant="success"] { background: $success_soft; color: $success; }
QLabel#badge[variant="warning"] { background: $warning_soft; color: $warning; }
QLabel#badge[variant="danger"] { background: $danger_soft; color: $danger; }
QLabel#langPill {
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 700;
    background: $accent_soft;
    color: $accent;
}
QLabel#modelAvatar {
    background: $accent_soft;
    color: $accent;
    border-radius: 12px;
    font-size: 17px;
    font-weight: 700;
}
QLabel#keycap {
    background: $keycap;
    border: 1px solid $keycap_border;
    border-bottom: 2px solid $keycap_border;
    border-radius: 6px;
    padding: 3px 8px;
    font-family: $mono;
    font-size: 12px;
    font-weight: 600;
}
QLabel#bigKeycap {
    background: $keycap;
    border: 1px solid $keycap_border;
    border-bottom: 3px solid $keycap_border;
    border-radius: 9px;
    padding: 8px 16px;
    font-family: $mono;
    font-size: 16px;
    font-weight: 600;
}
QPushButton {
    background: $surface2;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 7px 14px;
    min-height: 18px;
    font-weight: 500;
}
QPushButton:hover { background: $elevated; border-color: $border_strong; }
QPushButton:pressed { background: $input; }
QPushButton:disabled { color: $muted; background: $surface2; border-color: $border; }
QPushButton#primary {
    background: $accent;
    color: #FFFFFF;
    border: 1px solid $accent;
    font-weight: 600;
}
QPushButton#primary:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#primary:disabled { background: $accent_soft; color: $muted; border-color: $accent_soft; }
QPushButton#ghost { background: transparent; border: 1px solid transparent; color: $muted; }
QPushButton#ghost:hover { background: $surface2; color: $text; }
QPushButton#link {
    background: transparent;
    border: none;
    color: $accent;
    padding: 2px 0;
    text-align: left;
}
QPushButton#link:hover { color: $accent_hover; text-decoration: underline; }
QPushButton#danger { background: transparent; border: 1px solid $border; color: $danger; }
QPushButton#danger:hover { background: $danger_soft; border-color: $danger; }
QPushButton#seg {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px 12px;
    color: $muted;
    font-weight: 500;
}
QPushButton#seg:hover { color: $text; background: $surface2; }
QPushButton#seg:checked {
    background: $surface;
    border-color: $border_strong;
    color: $text;
}
QPushButton#tab {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    color: $muted;
    font-weight: 600;
}
QPushButton#tab:hover { color: $text; background: $surface2; }
QPushButton#tab:checked { background: $surface2; color: $text; }
QPushButton#keycapButton {
    background: $keycap;
    border: 1px solid $keycap_border;
    border-bottom: 2px solid $keycap_border;
    border-radius: 8px;
    padding: 6px 14px;
    font-family: $mono;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#keycapButton:hover { border-color: $accent; }
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 5px;
}
QToolButton:hover { background: $surface2; border-color: $border; }
QLineEdit, QComboBox {
    background: $input;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 7px 11px;
    min-height: 18px;
    selection-background-color: $selection;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QLineEdit:disabled, QComboBox:disabled { color: $muted; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView {
    background: $elevated;
    border: 1px solid $border_strong;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: $accent_soft;
    selection-color: $text;
    outline: none;
}
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $scroll_hover; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar {
    background: $surface2;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QCheckBox { spacing: 9px; color: $text; }
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid $border_strong;
    background: $input;
}
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }
QMenu {
    background: $elevated;
    border: 1px solid $border_strong;
    border-radius: 9px;
    padding: 6px;
}
QMenu::item { padding: 6px 18px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QToolTip {
    background: $elevated;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 5px 8px;
}
QMessageBox { background: $bg; }
QMessageBox QLabel { color: $text; }
"""
)


class ThemeManager(QObject):
    changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.name = "dark"

    @property
    def colors(self) -> dict[str, str]:
        return THEMES.get(self.name, THEMES["dark"])

    def set(self, name: str) -> None:
        name = name if name in THEMES else "dark"
        if name == self.name:
            return
        self.name = name
        self.changed.emit(name)


theme_manager = ThemeManager()


def stylesheet(name: str) -> str:
    colors = THEMES.get(name, THEMES["dark"])
    return QSS_TEMPLATE.substitute(**colors, font=FONT_FAMILY, mono=MONO_FAMILY)


def apply_theme(app: QApplication, name: str) -> None:
    theme_manager.set(name)
    colors = THEMES.get(name, THEMES["dark"])
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors["bg"]))
    palette.setColor(QPalette.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.Base, QColor(colors["input"]))
    palette.setColor(QPalette.AlternateBase, QColor(colors["surface2"]))
    palette.setColor(QPalette.Text, QColor(colors["text"]))
    palette.setColor(QPalette.Button, QColor(colors["surface2"]))
    palette.setColor(QPalette.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipBase, QColor(colors["elevated"]))
    palette.setColor(QPalette.ToolTipText, QColor(colors["text"]))
    palette.setColor(QPalette.PlaceholderText, QColor(colors["muted"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["muted"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(name))


def enable_dark_title_bar(widget: QWidget, dark: bool) -> None:
    """Pinta la barra de títol nativa de Windows en fosc o clar."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except Exception:  # noqa: BLE001
        pass


def set_variant(widget: QWidget, name: str, value: str) -> None:
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
