"""Backend Windows: hotkeys, inserció, instància única i sons.

Aquest mòdul només s'importa quan `sys.platform == "win32"`. La resta de
l'aplicació hi accedeix a través de les façanes `app.insert`, `app.hotkeys`,
`app.instance` i `app.feedback`.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

from app.backends.base import InsertAborted

# --------------------------------------------------------------------- hotkeys

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


# ------------------------------------------------------------------- inserció

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


def modifiers_down() -> bool:
    return any(key_is_down(vk) for vk in (VK_CONTROL, VK_SHIFT, VK_MENU))


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


# ------------------------------------------------------------------- instància

ERROR_ALREADY_EXISTS = 183

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = (
    wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR,
)
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL


class SingleInstance:
    def __init__(self, name: str = r"Local\CustormWispeFlow") -> None:
        self.name = name
        self.handle = None
        self.already_running = False
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self.handle and kernel32 is not None:
            kernel32.CloseHandle(self.handle)
            self.handle = None


# ------------------------------------------------------------------------ so

def beep(frequency: int, duration: int) -> None:
    import winsound

    winsound.Beep(frequency, duration)
