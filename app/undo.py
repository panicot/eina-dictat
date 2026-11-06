"""Desfer l'ultima insercio.

Nomes s'actua si la finestra en primer pla es la mateixa on es va inserir el
text: enviar retrocessos a una altra aplicacio seria destructiu. Els modificadors
s'esperen fins que es deixen anar, perque si no F9 amb Shift polsat enviaria
Ctrl+Shift+Z (redo) en lloc de Ctrl+Z.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from app.backends import backend
from app.insert import (
    foreground_window as get_foreground_window,
    send_backspaces,
    send_ctrl_z,
)

MAX_BACKSPACES = 500


@dataclass(frozen=True)
class LastInsert:
    text: str
    method: str
    hwnd: int
    chars: int


class Undoer:
    """Logica de desfer amb dependencias injectables per poder provar-la."""

    def __init__(
        self,
        foreground: Callable[[], int] = get_foreground_window,
        ctrl_z: Callable[[], None] = send_ctrl_z,
        backspaces: Callable[[int], None] = send_backspaces,
        modifiers_down: Callable[[], bool] = backend.modifiers_down,
        max_backspaces: int = MAX_BACKSPACES,
    ) -> None:
        self.foreground = foreground
        self.ctrl_z = ctrl_z
        self.backspaces = backspaces
        self.modifiers_down = modifiers_down
        self.max_backspaces = max_backspaces

    def undo(self, last: LastInsert | None) -> tuple[bool, str]:
        if last is None:
            return False, "No hi ha cap insercio per desfer."
        if last.method not in ("type", "paste"):
            return False, "Aquesta insercio no es pot desfer."
        if self.foreground() != last.hwnd:
            return False, ("No desfaig res: la finestra activa no es la mateixa "
                           "on es va inserir el text.")
        self._wait_modifiers()
        if last.method == "paste":
            self.ctrl_z()
            return True, "Desfet amb Ctrl+Z."
        count = min(last.chars, self.max_backspaces)
        self.backspaces(count)
        if count < last.chars:
            return True, f"Desfets {count} de {last.chars} caracters (limit)."
        return True, f"Desfets {count} caracters amb retroces."

    def _wait_modifiers(self, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.modifiers_down():
                return
            time.sleep(0.02)
