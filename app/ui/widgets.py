"""Widgets propis de la interfície."""

from __future__ import annotations

import math
import time
from collections import deque

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from app import hotkeys
from app.ui.icons import icon, pixmap
from app.ui.theme import theme_manager


def logo_pixmap(size: int = 36) -> QPixmap:
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0, 0, size * scale, size * scale)
    path = QPainterPath()
    path.addRoundedRect(rect, size * scale * 0.28, size * scale * 0.28)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, QColor(theme_manager.colors["accent"]))
    gradient.setColorAt(1, QColor("#4FD1C5"))
    painter.fillPath(path, gradient)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    unit = size * scale
    bars = ((0.28, 0.26), (0.46, 0.48), (0.64, 0.34))
    for x, height in bars:
        bar = QRectF(unit * x, unit * (0.5 - height / 2), unit * 0.075,
                     unit * height)
        painter.drawRoundedRect(bar, unit * 0.04, unit * 0.04)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def app_icon() -> QIcon:
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        result.addPixmap(logo_pixmap(size))
    return result


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, margins: tuple[int, int, int, int] = (20, 18, 20, 18)) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(12)


class SectionLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setObjectName("section")


class Badge(QLabel):
    def __init__(self, text: str = "", variant: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("badge")
        self.setAlignment(Qt.AlignCenter)
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        self.setProperty("variant", variant)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFixedHeight(1)


class ComboBox(QComboBox):
    """QComboBox amb un chevron propi, consistent als dos temes."""

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(theme_manager.colors["muted"])
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        x = self.width() - 15
        y = self.height() / 2 - 2
        path = QPainterPath()
        path.moveTo(x - 4, y)
        path.lineTo(x, y + 4)
        path.lineTo(x + 4, y)
        painter.drawPath(path)
        painter.end()


class SegmentedControl(QFrame):
    changed = Signal(int)

    def __init__(self, items: list[tuple[str, str | None]], object_name: str = "segmented",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.items = items
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        for index, (text, icon_name) in enumerate(items):
            button = QPushButton(text)
            button.setObjectName("tab" if object_name == "tabBar" else "seg")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            if icon_name:
                button.setIcon(icon(icon_name, theme_manager.colors["muted"], 16))
                button.setIconSize(QSize(16, 16))
            self._group.addButton(button, index)
            layout.addWidget(button)
            self._buttons.append(button)
        self._group.idClicked.connect(self.changed.emit)
        self._group.idClicked.connect(lambda _index: self._refresh_icons())
        theme_manager.changed.connect(self._refresh_icons)

    def _refresh_icons(self) -> None:
        names = ["gear", "download"]
        for index, button in enumerate(self._buttons):
            if index < len(names) and button.icon().isNull() is False:
                color = (theme_manager.colors["text"]
                         if button.isChecked() else theme_manager.colors["muted"])
                button.setIcon(icon(names[index], color, 16))

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self._refresh_icons()

    def current(self) -> int:
        return self._group.checkedId()

    def button(self, index: int) -> QPushButton:
        return self._buttons[index]


class StatusDot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = QColor(theme_manager.colors["success"])
        self._pulse = 0.0
        self._animated = False
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state: str) -> None:
        colors = theme_manager.colors
        mapping = {
            "idle": colors["success"],
            "listening": colors["accent"],
            "transcribing": colors["warning"],
            "error": colors["danger"],
            "paused": colors["muted"],
        }
        self._color = QColor(mapping.get(state, colors["muted"]))
        self._animated = state in {"listening", "transcribing"}
        if self._animated:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._pulse = 0.0
        self.update()

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.12) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(self._color)
        if self._animated:
            color.setAlphaF(0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._pulse)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(1, 1, 8, 8))
        painter.end()


class StatusChip(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 4, 10, 4)
        layout.setSpacing(7)
        self.dot = StatusDot(self)
        self.label = QLabel("A punt")
        self.label.setObjectName("caption")
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self._language = "ca"

    def set_state(self, state: str, language: str | None = None) -> None:
        if language:
            self._language = language
        texts = {
            "idle": f"A punt · {self._language.upper()}",
            "listening": "Escoltant",
            "transcribing": "Transcrivint",
            "error": "Error",
            "paused": "En pausa",
        }
        self.label.setText(texts.get(state, "A punt"))
        self.dot.set_state(state)

    def set_language(self, language: str) -> None:
        self._language = language
        if self.label.text().startswith("A punt"):
            self.label.setText(f"A punt · {language.upper()}")


class CheckBox(QCheckBox):
    """QCheckBox amb una marca blanca llegible als dos temes."""

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, option, self
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#FFFFFF"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(rect.x() + rect.width() * 0.26,
                    rect.y() + rect.height() * 0.52)
        path.lineTo(rect.x() + rect.width() * 0.43,
                    rect.y() + rect.height() * 0.70)
        path.lineTo(rect.x() + rect.width() * 0.76,
                    rect.y() + rect.height() * 0.30)
        painter.drawPath(path)
        painter.end()


class KeycapButton(QPushButton):
    def __init__(self, combo: str = "f8", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("keycapButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Fes clic per capturar una tecla o combinació")
        self.set_combo(combo)

    def set_combo(self, combo: str) -> None:
        self._combo = combo
        self.setText(" + ".join(part.upper() for part in combo.split("+")))

    def combo(self) -> str:
        return self._combo


class LevelMeter(QWidget):
    def __init__(self, bars: int = 20, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._levels: deque[float] = deque([0.0] * bars, maxlen=bars)
        self._active = False
        self.setMinimumHeight(26)
        self.setMinimumWidth(140)

    def push(self, level: float) -> None:
        self._levels.append(max(0.0, min(1.0, level)))
        self._active = True
        self.update()

    def reset(self) -> None:
        self._levels = deque([0.0] * self._levels.maxlen, maxlen=self._levels.maxlen)
        self._active = False
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colors = theme_manager.colors
        count = len(self._levels)
        gap = 2.0
        width = (self.width() - gap * (count - 1)) / count
        for index, level in enumerate(self._levels):
            if level <= 0.01:
                color = QColor(colors["border"])
            elif level < 0.62:
                color = QColor(colors["success"])
            elif level < 0.85:
                color = QColor(colors["warning"])
            else:
                color = QColor(colors["danger"])
            if not self._active:
                color.setAlpha(110)
            height = max(3.0, level * (self.height() - 2))
            x = index * (width + gap)
            y = (self.height() - height) / 2
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y, width, height), 1.5, 1.5)
        painter.end()


class Toast(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 14, 9)
        layout.setSpacing(9)
        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        self._text = QLabel()
        self._text.setWordWrap(True)
        layout.addWidget(self._icon)
        layout.addWidget(self._text)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(160)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide)
        self.hide()

    def show_message(self, text: str, kind: str = "info", duration: int = 2600) -> None:
        colors = theme_manager.colors
        icon_name = {"info": "check", "error": "close", "warning": "sparkle"}.get(kind, "check")
        color = {"info": colors["success"], "error": colors["danger"],
                 "warning": colors["warning"]}.get(kind, colors["success"])
        self._icon.setPixmap(pixmap(icon_name, color, 16))
        self._text.setText(text)
        self._text.setToolTip(text)
        max_width = max(260, min(520, self.parentWidget().width() - 80))
        self.setMaximumWidth(max_width)
        available = max(120, max_width - 56)
        natural = self._text.fontMetrics().horizontalAdvance(text)
        self._text.setFixedWidth(min(available, max(120, natural + 2)))
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._effect.setOpacity(0.0)
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(duration)

    def _hide(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._after_hide)
        self._fade.start()

    def _after_hide(self) -> None:
        try:
            self._fade.finished.disconnect(self._after_hide)
        except (TypeError, RuntimeError):
            pass
        self.hide()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = parent.width() - self.width() - 24
        y = parent.height() - self.height() - 82
        self.move(QPoint(max(16, x), max(16, y)))


def _key_name(event) -> str | None:  # noqa: ANN001
    key = event.key()
    if Qt.Key_F1 <= key <= Qt.Key_F24:
        return f"f{key - Qt.Key_F1 + 1}"
    if Qt.Key_A <= key <= Qt.Key_Z:
        return chr(key).lower()
    if Qt.Key_0 <= key <= Qt.Key_9:
        return chr(key)
    mapping = {
        Qt.Key_Space: "space",
        Qt.Key_Tab: "tab",
        Qt.Key_Escape: "esc",
        Qt.Key_Return: "enter",
        Qt.Key_Enter: "enter",
        Qt.Key_Backspace: "backspace",
        Qt.Key_Delete: "delete",
        Qt.Key_Insert: "insert",
        Qt.Key_Home: "home",
        Qt.Key_End: "end",
        Qt.Key_PageUp: "pageup",
        Qt.Key_PageDown: "pagedown",
        Qt.Key_Up: "up",
        Qt.Key_Down: "down",
        Qt.Key_Left: "left",
        Qt.Key_Right: "right",
        Qt.Key_CapsLock: "capslock",
        Qt.Key_Pause: "pause",
        Qt.Key_ScrollLock: "scrolllock",
    }
    return mapping.get(key)


def _key_combo(event) -> str | None:  # noqa: ANN001
    if event.key() in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
        return None
    name = _key_name(event)
    if not name:
        return None
    modifiers = event.modifiers()
    parts = []
    if modifiers & Qt.ControlModifier:
        parts.append("ctrl")
    if modifiers & Qt.AltModifier:
        parts.append("alt")
    if modifiers & Qt.ShiftModifier:
        parts.append("shift")
    if modifiers & Qt.MetaModifier:
        parts.append("win")
    parts.append(name)
    return "+".join(parts)


class HotkeyDialog(QDialog):
    def __init__(self, current: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Captura la tecla")
        self.setModal(True)
        self.setFixedWidth(460)
        self.combo_value = current
        self._accepted = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        title = QLabel("Prem la tecla o combinació")
        title.setObjectName("cardTitle")
        description = QLabel(
            "Fes servir F1–F24, una lletra, un número o una combinació amb Ctrl, Alt, Shift o Win. "
            "Prem Esc per cancel·lar."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        self.display = QLabel()
        self.display.setObjectName("bigKeycap")
        self.display.setAlignment(Qt.AlignCenter)
        self.error = QLabel("")
        self.error.setObjectName("danger")
        self.error.setWordWrap(True)
        cancel = QPushButton("Cancel·la")
        cancel.clicked.connect(self.reject)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.display, 0, Qt.AlignHCenter)
        layout.addWidget(self.error)
        layout.addWidget(cancel, 0, Qt.AlignRight)
        self._show_combo(current)

    def _show_combo(self, combo: str) -> None:
        self.display.setText(" + ".join(part.upper() for part in combo.split("+")))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        combo = _key_combo(event)
        if combo is None:
            event.accept()
            return
        try:
            hotkeys.parse(combo)
        except ValueError as exc:
            self.error.setText(str(exc))
            event.accept()
            return
        self.error.setText("")
        self.combo_value = combo
        self._show_combo(combo)
        if not self._accepted:
            self._accepted = True
            QTimer.singleShot(180, self.accept)
        event.accept()

    def combo(self) -> str:
        return self.combo_value


class MicTestDialog(QDialog):
    def __init__(self, device: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prova el micròfon")
        self.setModal(True)
        self.setFixedSize(460, 280)
        self.device = device or None
        self._stream = None
        self._level = 0.0
        self._peak = 0.0
        self._deadline = 0.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        title = QLabel("Parla ara")
        title.setObjectName("cardTitle")
        self.description = QLabel("Escoltant el micròfon durant 5 segons…")
        self.description.setObjectName("muted")
        self.meter = LevelMeter(bars=24)
        self.meter.setMinimumHeight(54)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        close = QPushButton("Tanca")
        close.clicked.connect(self.accept)
        layout.addWidget(title)
        layout.addWidget(self.description)
        layout.addWidget(self.meter)
        layout.addWidget(self.result)
        layout.addStretch(1)
        layout.addWidget(close, 0, Qt.AlignRight)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        QTimer.singleShot(50, self._start)

    def _start(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            info = sd.query_devices(self.device, kind="input")
            samplerate = int(info["default_samplerate"])
            self._stream = sd.InputStream(
                device=self.device, channels=1, samplerate=samplerate,
                dtype="float32", callback=self._callback,
            )
            self._stream.start()
            self._deadline = time.monotonic() + 5.0
            self._timer.start()
        except Exception as exc:  # noqa: BLE001
            self.description.setText("No s'ha pogut obrir el micròfon.")
            self.result.setObjectName("danger")
            self.result.setText(str(exc))
            style = self.result.style()
            style.unpolish(self.result)
            style.polish(self.result)

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        try:
            import numpy as np

            value = float(np.sqrt(np.mean(indata * indata)))
            self._level = value
            self._peak = max(self._peak, value)
        except Exception:  # noqa: BLE001
            pass

    def _tick(self) -> None:
        remaining = max(0.0, self._deadline - time.monotonic())
        self.meter.push(min(1.0, self._level * 9.0))
        self.description.setText(f"Escoltant… {remaining:.1f} s")
        if remaining <= 0:
            self._stop()
            if self._peak > 0.008:
                self.description.setText("Prova completada")
                self.result.setObjectName("success")
                self.result.setText("S'ha detectat àudio correctament.")
            else:
                self.description.setText("Prova completada")
                self.result.setObjectName("warning")
                self.result.setText(
                    "No s'ha detectat veu. Comprova el micròfon triat i els permisos de Windows."
                )
            style = self.result.style()
            style.unpolish(self.result)
            style.polish(self.result)

    def _stop(self) -> None:
        self._timer.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop()
        super().closeEvent(event)
