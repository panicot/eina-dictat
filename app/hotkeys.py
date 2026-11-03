"""Hotkeys globals sense hooks: consulta periodica de GetAsyncKeyState.

Aixo evita problemes de compatibilitat dels hooks de baix nivell i no requereix
permisos d'administrador. Tambe permet mode mantenir (press/release).
"""

from __future__ import annotations

import ctypes
import threading
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)

MODIFIERS = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
}

KEYS = {
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "capslock": 0x14,
    "pause": 0x13,
    "scrolllock": 0x91,
    "right ctrl": 0xA3,
    "right alt": 0xA5,
    "right shift": 0xA1,
    "left ctrl": 0xA2,
}


def parse(combo: str) -> tuple[list[int], int]:
    """'ctrl+alt+1' -> ([0x11, 0x12], 0x31)."""
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    if not parts:
        raise ValueError("Hotkey buida")
    *modifier_names, key_name = parts
    modifiers = []
    for name in modifier_names:
        if name not in MODIFIERS:
            raise ValueError(f"Modificador desconegut: {name}")
        modifiers.append(MODIFIERS[name])

    if key_name in KEYS:
        vk = KEYS[key_name]
    elif key_name in MODIFIERS:
        vk = MODIFIERS[key_name]
    elif len(key_name) == 1 and key_name.isalnum():
        vk = ord(key_name.upper())
    else:
        raise ValueError(f"Tecla desconeguda: {key_name}")
    return modifiers, vk


class HotkeyManager:
    def __init__(self, interval: float = 0.025) -> None:
        self.interval = interval
        self._bindings: list[tuple[list[int], int, object, object | None]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def add(self, combo: str, on_press, on_release=None) -> None:  # noqa: ANN001
        modifiers, vk = parse(combo)
        self._bindings.append((modifiers, vk, on_press, on_release))

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _is_down(self, vk: int) -> bool:
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def _loop(self) -> None:
        states = [False] * len(self._bindings)
        while not self._stop.is_set():
            for index, (modifiers, vk, on_press, on_release) in enumerate(self._bindings):
                active = self._is_down(vk) and all(self._is_down(m) for m in modifiers)
                if active and not states[index]:
                    states[index] = True
                    threading.Thread(target=on_press, daemon=True).start()
                elif not active and states[index]:
                    states[index] = False
                    if on_release is not None:
                        threading.Thread(target=on_release, daemon=True).start()
            time.sleep(self.interval)

    def stop(self) -> None:
        self._stop.set()
