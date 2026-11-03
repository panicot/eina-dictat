"""Insercio de text a qualsevol aplicacio de Windows.

Dues vies:
  - SendInput amb KEYEVENTF_UNICODE: escriu caracter a caracter, respecta el
    cursor i no toca el porta-retalls.
  - Porta-retalls + Ctrl+V: mes rapid en textos llargs i unic cami fiable cap a
    finestres elevades (UIPI).
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_RETURN = 0x0D
VK_TAB = 0x09
VK_CONTROL = 0x11
VK_V = 0x56
VK_BACK = 0x08
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_Z = 0x5A


class InsertAborted(RuntimeError):
    """La finestra en primer pla ha canviat durant la insercio."""

    def __init__(self, chars_written: int = 0) -> None:
        super().__init__("La finestra activa ha canviat durant la insercio.")
        self.chars_written = chars_written


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _key_input(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD,
                 u=_INPUTUNION(ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags,
                                             time=0, dwExtraInfo=0)))


def _send(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def _utf16_units(text: str):
    raw = text.encode("utf-16-le")
    for i in range(0, len(raw), 2):
        yield int.from_bytes(raw[i:i + 2], "little")


def foreground_window() -> int:
    return int(user32.GetForegroundWindow())


def _focus_ok(expected_hwnd: int | None) -> bool:
    return expected_hwnd is None or foreground_window() == expected_hwnd


def type_text(text: str, expected_hwnd: int | None = None) -> int:
    """Escriu text amb SendInput Unicode. Retorna el nombre de caracters.

    Si es passa `expected_hwnd`, s'avorta (InsertAborted) abans de cada lot si
    la finestra en primer pla ja no es la mateixa.
    """
    if not text:
        return 0
    if not _focus_ok(expected_hwnd):
        raise InsertAborted(0)
    written = 0
    pending = 0
    batch: list[INPUT] = []
    for code in _utf16_units(text):
        if code == 0x0A:  # \n
            batch.append(_key_input(vk=VK_RETURN))
            batch.append(_key_input(vk=VK_RETURN, flags=KEYEVENTF_KEYUP))
        elif code == 0x09:  # \t
            batch.append(_key_input(vk=VK_TAB))
            batch.append(_key_input(vk=VK_TAB, flags=KEYEVENTF_KEYUP))
        else:
            batch.append(_key_input(scan=code, flags=KEYEVENTF_UNICODE))
            batch.append(_key_input(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        pending += 1
        if len(batch) >= 100:
            if not _focus_ok(expected_hwnd):
                raise InsertAborted(written)
            _send(batch)
            written += pending
            pending = 0
            batch = []
            time.sleep(0.002)
    if batch:
        if not _focus_ok(expected_hwnd):
            raise InsertAborted(written)
        _send(batch)
        written += pending
    return len(text)


def send_ctrl_v() -> None:
    _send([
        _key_input(vk=VK_CONTROL),
        _key_input(vk=VK_V),
        _key_input(vk=VK_V, flags=KEYEVENTF_KEYUP),
        _key_input(vk=VK_CONTROL, flags=KEYEVENTF_KEYUP),
    ])


def send_ctrl_z() -> None:
    _send([
        _key_input(vk=VK_CONTROL),
        _key_input(vk=VK_Z),
        _key_input(vk=VK_Z, flags=KEYEVENTF_KEYUP),
        _key_input(vk=VK_CONTROL, flags=KEYEVENTF_KEYUP),
    ])


def send_backspaces(count: int) -> None:
    """Envia `count` retrocessos, en lots, per desfer text escrit amb SendInput."""
    remaining = max(0, count)
    while remaining > 0:
        batch = []
        for _ in range(min(remaining, 50)):
            batch.append(_key_input(vk=VK_BACK))
            batch.append(_key_input(vk=VK_BACK, flags=KEYEVENTF_KEYUP))
        _send(batch)
        remaining -= len(batch) // 2
        if remaining:
            time.sleep(0.002)


def key_is_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _clipboard_get() -> str | None:
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:  # noqa: BLE001
        return None


def _clipboard_set(text: str) -> bool:
    import pyperclip
    for _ in range(5):
        try:
            pyperclip.copy(text)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.05)
    return False


def paste_text(text: str, restore_clipboard: bool = True,
               expected_hwnd: int | None = None) -> int:
    """Enganxa text via porta-retalls + Ctrl+V. Retorna el nombre de caracters."""
    if not text:
        return 0
    previous = _clipboard_get() if restore_clipboard else None
    if not _clipboard_set(text):
        raise RuntimeError("No s'ha pogut escriure al porta-retalls")
    try:
        time.sleep(0.06)
        if not _focus_ok(expected_hwnd):
            raise InsertAborted(0)
        send_ctrl_v()
        # Espera que l'aplicacio de desti llegeixi el porta-retalls abans de restaurar.
        time.sleep(0.30)
    finally:
        if restore_clipboard and previous is not None:
            _clipboard_set(previous)
    return len(text)


def insert(text: str, mode: str = "auto", threshold: int = 120,
           restore_clipboard: bool = True,
           expected_hwnd: int | None = None) -> tuple[int, str]:
    """Insereix text. Retorna (caracters, metode emprat)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return 0, "none"

    use_paste = mode == "paste" or (mode == "auto" and len(text) > threshold)
    if use_paste:
        try:
            return paste_text(text, restore_clipboard, expected_hwnd), "paste"
        except InsertAborted:
            raise
        except Exception:  # noqa: BLE001
            return type_text(text, expected_hwnd), "type"
    return type_text(text, expected_hwnd), "type"
