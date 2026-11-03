"""Indicador flotant que no roba el focus."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from app.ui.theme import theme_manager


class OverlayWindow(QWidget):
    WIDTH = 370
    HEIGHT = 72

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowOpacity(0.0)
        self._state = "idle"
        self._mode = "idle"
        self._language = "ca"
        self._message = ""
        self._detail = ""
        self._started = 0.0
        self._transient_until = 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(170)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        theme_manager.changed.connect(self.update)

    # ------------------------------------------------------------------ public

    def set_state(self, state: str, language: str | None = None) -> None:
        if language:
            self._language = language
        if state == "idle":
            if time.monotonic() < self._transient_until:
                return
            self._state = "idle"
            self._schedule_hide(900)
            return
        self._state = state
        if state == "listening":
            self._mode = "listening"
            self._started = time.monotonic()
            self._message = "Escoltant…"
            self._detail = "00:00"
        elif state == "transcribing":
            self._mode = "transcribing"
            self._message = "Transcrivint…"
            if not self._started:
                self._started = time.monotonic()
        elif state == "error":
            self._mode = "error"
            self._message = "Error"
        self._transient_until = 0.0
        self._reveal()
        self._timer.start()

    def set_language(self, language: str) -> None:
        self._language = language
        self.update()

    def show_transcript(self, chars: int) -> None:
        self._mode = "done"
        self._state = "idle"
        self._message = "Text inserit"
        self._detail = f"{chars} caràcters" if chars != 1 else "1 caràcter"
        self._transient_until = time.monotonic() + 2.2
        self._reveal()
        self._schedule_hide(2400)

    def show_message(self, message: str, kind: str = "info", detail: str = "") -> None:
        self._mode = kind if kind in {"error", "warning"} else "info"
        self._message = message
        self._detail = detail
        self._transient_until = time.monotonic() + 2.8
        self._reveal()
        self._schedule_hide(3000)

    def show_error(self, message: str) -> None:
        short = message.splitlines()[0]
        self._mode = "error"
        self._state = "error"
        self._message = "No s'ha pogut dictar"
        self._detail = short[:64]
        self._transient_until = time.monotonic() + 3.5
        self._reveal()
        self._schedule_hide(3800)

    # ------------------------------------------------------------------ window

    def _reveal(self) -> None:
        self._hide_timer.stop()
        self._position()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start()

    def _schedule_hide(self, ms: int) -> None:
        self._hide_timer.start(ms)

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._after_fade)
        self._fade.start()

    def _after_fade(self) -> None:
        try:
            self._fade.finished.disconnect(self._after_fade)
        except (TypeError, RuntimeError):
            pass
        if self.windowOpacity() <= 0.01:
            self.hide()
            self._timer.stop()
            self._started = 0.0

    def _position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + area.height() - self.height() - 42
        self.move(x, y)

    def _tick(self) -> None:
        self._phase += 0.22
        if self._state == "listening" and self._started:
            elapsed = int(time.monotonic() - self._started)
            self._detail = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        self.update()

    # ------------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        colors = theme_manager.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        background = QColor(colors["overlay"])
        background.setAlpha(244)
        painter.fillPath(path, background)
        painter.setPen(QPen(QColor(colors["border_strong"]), 1))
        painter.drawPath(path)

        center_y = self.height() / 2
        if self._mode in {"listening", "transcribing"}:
            self._paint_bars(painter, 24, center_y, colors)
            text_x = 106
        elif self._mode == "done":
            self._paint_check(painter, 46, center_y, colors)
            text_x = 106
        elif self._mode == "error":
            self._paint_error(painter, 46, center_y, colors)
            text_x = 106
        else:
            self._paint_info(painter, 46, center_y, colors)
            text_x = 106

        primary = QFont("Segoe UI", 10)
        primary.setWeight(QFont.DemiBold)
        painter.setFont(primary)
        painter.setPen(QColor(colors["text"]))
        painter.drawText(
            QRectF(text_x, 16, self.width() - text_x - 78, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._message,
        )

        secondary = QFont("Segoe UI", 8)
        painter.setFont(secondary)
        painter.setPen(QColor(colors["muted"]))
        detail = self._detail
        if self._state == "listening":
            detail = f"{detail} · {self._language.upper()}"
        elif self._state == "transcribing":
            detail = f"Model local · {self._language.upper()}"
        painter.drawText(
            QRectF(text_x, 37, self.width() - text_x - 76, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            detail,
        )

        if self._mode in {"listening", "transcribing"}:
            badge = self._language.upper()
            badge_font = QFont("Segoe UI", 8)
            badge_font.setWeight(QFont.Bold)
            painter.setFont(badge_font)
            metrics = painter.fontMetrics()
            width = max(30, metrics.horizontalAdvance(badge) + 16)
            badge_rect = QRectF(self.width() - width - 18, center_y - 11, width, 22)
            badge_path = QPainterPath()
            badge_path.addRoundedRect(badge_rect, 7, 7)
            painter.fillPath(badge_path, QColor(colors["accent_soft"]))
            painter.setPen(QColor(colors["accent"]))
            painter.drawText(badge_rect, Qt.AlignCenter, badge)
        painter.end()

    def _paint_bars(self, painter: QPainter, x: float, center_y: float,
                    colors: dict[str, str]) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors["accent"]))
        for index in range(9):
            if self._mode == "transcribing":
                wave = 0.35 + 0.65 * abs(math.sin(self._phase * 0.7 - index * 0.55))
            else:
                wave = 0.25 + 0.75 * abs(math.sin(self._phase - index * 0.63))
            height = 8 + wave * 26
            bar = QRectF(x + index * 7, center_y - height / 2, 4.5, height)
            painter.drawRoundedRect(bar, 2.2, 2.2)

    def _paint_check(self, painter: QPainter, x: float, center_y: float,
                     colors: dict[str, str]) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors["success_soft"]))
        painter.drawEllipse(QRectF(x - 17, center_y - 17, 34, 34))
        pen = QPen(QColor(colors["success"]), 2.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(x - 7, center_y)
        path.lineTo(x - 2, center_y + 5)
        path.lineTo(x + 8, center_y - 6)
        painter.drawPath(path)

    def _paint_error(self, painter: QPainter, x: float, center_y: float,
                     colors: dict[str, str]) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors["danger_soft"]))
        painter.drawEllipse(QRectF(x - 17, center_y - 17, 34, 34))
        pen = QPen(QColor(colors["danger"]), 2.4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(x - 6, center_y - 6, x + 6, center_y + 6)
        painter.drawLine(x + 6, center_y - 6, x - 6, center_y + 6)

    def _paint_info(self, painter: QPainter, x: float, center_y: float,
                    colors: dict[str, str]) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors["accent_soft"]))
        painter.drawEllipse(QRectF(x - 17, center_y - 17, 34, 34))
        pen = QPen(QColor(colors["accent"]), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(x, center_y - 7, x, center_y + 2)
        painter.drawPoint(x, center_y + 8)
