"""Backend Linux: X11 i Wayland.

- **X11**: hotkeys amb `pynput`, inserció amb `xdotool` i porta-retalls via
  `pyperclip`/`xclip`.
- **Wayland**: hotkeys amb `evdev`, inserció amb `ydotool` (o `wtype`) i
  porta-retalls amb `wl-clipboard`.

La sessió es detecta amb `XDG_SESSION_TYPE` i `WAYLAND_DISPLAY`. Es pot forçar
amb la variable d'entorn `CWF_BACKEND=x11` o `CWF_BACKEND=wayland`.
"""

from __future__ import annotations

import logging
import os
import selectors
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.backends.base import InsertAborted

log = logging.getLogger("cwf")

# --------------------------------------------------------------------- hotkeys

_MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super",
    "win": "super",
    "meta": "super",
    "cmd": "super",
}

_SPECIAL_KEYS = {
    "space": "space",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "esc": "escape",
    "escape": "escape",
    "backspace": "backspace",
    "delete": "delete",
    "insert": "insert",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "capslock": "capslock",
    "pause": "pause",
    "scrolllock": "scrolllock",
    "right ctrl": "right ctrl",
    "right alt": "right alt",
    "right shift": "right shift",
    "left ctrl": "left ctrl",
}

_SPECIAL_KEY_NAMES = (
    set(_SPECIAL_KEYS.values())
    | set(_MODIFIER_ALIASES.values())
    | {f"f{i}" for i in range(1, 25)}
)

# Exportats per la façana `app.hotkeys`.
MODIFIERS = set(_MODIFIER_ALIASES)
KEYS = _SPECIAL_KEY_NAMES


@dataclass(frozen=True)
class ParsedHotkey:
    modifiers: tuple[str, ...]
    key: str


def parse(combo: str) -> ParsedHotkey:
    """Valida i normalitza una combinació de tecles.

    Els noms resultants són independents de la plataforma. La conversió a
    objectes de `pynput` o codis d'`evdev` es fa quan el gestor arrenca.
    """
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    if not parts:
        raise ValueError("Hotkey buida")

    *modifier_names, key_name = parts
    modifiers: list[str] = []
    for name in modifier_names:
        canonical = _MODIFIER_ALIASES.get(name)
        if canonical is None:
            raise ValueError(f"Modificador desconegut: {name}")
        if canonical not in modifiers:
            modifiers.append(canonical)

    key = _SPECIAL_KEYS.get(key_name, key_name)
    if key in _MODIFIER_ALIASES:
        key = _MODIFIER_ALIASES[key]
    if key not in _SPECIAL_KEY_NAMES and not (len(key) == 1 and key.isalnum()):
        raise ValueError(f"Tecla desconeguda: {key_name}")
    return ParsedHotkey(tuple(modifiers), key)


def _session_is_wayland() -> bool:
    override = os.environ.get("CWF_BACKEND", "").strip().lower()
    if override in ("x11", "xorg"):
        return False
    if override in ("wayland", "wl"):
        return True

    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if session_type == "wayland":
        return True
    if session_type in ("x11", "xorg"):
        return False
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _require_x11(feature: str) -> None:
    if _session_is_wayland():
        raise RuntimeError(
            f"{feature}: la sessió actual és Wayland. "
            "Fes servir una sessió X11 o `CWF_BACKEND=x11`."
        )
    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            f"{feature}: no s'ha detectat cap sessió X11 (falta la variable DISPLAY)."
        )


def _modifier_maps(keyboard) -> tuple[dict[str, set[object]], dict[object, str]]:  # noqa: ANN001
    names = {
        "ctrl": ("ctrl", "ctrl_l", "ctrl_r"),
        "alt": ("alt", "alt_l", "alt_r"),
        "shift": ("shift", "shift_l", "shift_r"),
        "super": ("cmd", "cmd_l", "cmd_r"),
    }
    key_sets: dict[str, set[object]] = {}
    reverse: dict[object, str] = {}
    for canonical, attrs in names.items():
        values = {
            getattr(keyboard.Key, attr)
            for attr in attrs
            if hasattr(keyboard.Key, attr)
        }
        key_sets[canonical] = values
        for value in values:
            reverse[value] = canonical
    return key_sets, reverse


def _to_pynput_key(keyboard, key_name: str):  # noqa: ANN001
    key = keyboard.Key
    special = {
        "space": key.space,
        "enter": key.enter,
        "tab": key.tab,
        "escape": key.esc,
        "backspace": key.backspace,
        "delete": key.delete,
        "insert": key.insert,
        "home": key.home,
        "end": key.end,
        "pageup": key.page_up,
        "pagedown": key.page_down,
        "up": key.up,
        "down": key.down,
        "left": key.left,
        "right": key.right,
        "capslock": key.caps_lock,
        "pause": key.pause,
        "scrolllock": key.scroll_lock,
        "right ctrl": key.ctrl_r,
        "right alt": key.alt_r,
        "right shift": key.shift_r,
        "left ctrl": key.ctrl_l,
    }
    if key_name in special:
        return special[key_name]
    if key_name.startswith("f") and key_name[1:].isdigit():
        return getattr(key, key_name)
    if len(key_name) == 1:
        return keyboard.KeyCode.from_char(key_name)
    raise ValueError(f"Tecla desconeguda: {key_name}")


# ----------------------------------------------------------------- evdev (Wayland)

# Noms de tecles d'evdev. Les lletres, els dígits i les tecles F es resolen
# directament a partir del nom (`a` -> KEY_A, `1` -> KEY_1, `f8` -> KEY_F8).
_EVDEV_SPECIAL = {
    "space": "KEY_SPACE",
    "enter": "KEY_ENTER",
    "tab": "KEY_TAB",
    "escape": "KEY_ESC",
    "backspace": "KEY_BACKSPACE",
    "delete": "KEY_DELETE",
    "insert": "KEY_INSERT",
    "home": "KEY_HOME",
    "end": "KEY_END",
    "pageup": "KEY_PAGEUP",
    "pagedown": "KEY_PAGEDOWN",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "capslock": "KEY_CAPSLOCK",
    "pause": "KEY_PAUSE",
    "scrolllock": "KEY_SCROLLLOCK",
    "right ctrl": "KEY_RIGHTCTRL",
    "right alt": "KEY_RIGHTALT",
    "right shift": "KEY_RIGHTSHIFT",
    "left ctrl": "KEY_LEFTCTRL",
    "ctrl": "KEY_LEFTCTRL",
    "alt": "KEY_LEFTALT",
    "shift": "KEY_LEFTSHIFT",
    "super": "KEY_LEFTMETA",
}


def _evdev_attr(key_name: str) -> str:
    if key_name in _EVDEV_SPECIAL:
        return _EVDEV_SPECIAL[key_name]
    if key_name.startswith("f") and key_name[1:].isdigit():
        return f"KEY_{key_name.upper()}"
    if len(key_name) == 1 and key_name.isalnum():
        return f"KEY_{key_name.upper()}"
    raise ValueError(f"Tecla desconeguda per a evdev: {key_name}")


def _evdev_code(ecodes, key_name: str) -> int:  # noqa: ANN001
    attr = _evdev_attr(key_name)
    try:
        return int(getattr(ecodes, attr))
    except AttributeError as exc:
        raise ValueError(
            f"La tecla {key_name!r} ({attr}) no existeix en aquest sistema."
        ) from exc


def _evdev_modifier_sets(ecodes) -> dict[str, set[int]]:  # noqa: ANN001
    return {
        "ctrl": {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL},
        "alt": {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT},
        "shift": {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT},
        "super": {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA},
    }


_INPUT_PERMISSION_HINT = (
    "No es pot llegir cap teclat de /dev/input (permisos insuficients).\n"
    "Afegeix el teu usuari al grup `input` i torna a iniciar la sessió:\n"
    "  sudo usermod -aG input $USER\n"
    "Si prefereixes no fer servir el grup `input`, crea una regla udev que "
    "doni accés de lectura a /dev/input/event*."
)

_EVDEV_INSTALL_HINT = (
    "Falta el mòdul `evdev` per llegir els hotkeys a Wayland. "
    "Instal·la'l amb `pip install evdev` o amb el paquet del sistema "
    "(`python3-evdev` a Debian/Ubuntu i Fedora)."
)

_INJECTOR_INSTALL_HINT = (
    "Falta `ydotool` o `wtype` per injectar text a Wayland. "
    "Instal·la `ydotool` (recomanat) o `wtype` amb el gestor de paquets."
)

_CLIPBOARD_INSTALL_HINT = (
    "Falta `wl-clipboard`. Instal·la'l amb el gestor de paquets "
    "(`sudo apt install wl-clipboard` o `sudo dnf install wl-clipboard`)."
)

_YDOTOOLD_HINT = (
    "Comprova que el dimoni `ydotoold` estigui en marxa "
    "(`systemctl --user start ydotool` o `ydotoold &`)."
)


def _open_evdev_keyboards() -> tuple[list[object], list[str]]:
    """Obre els teclats llegibles de `/dev/input`.

    Retorna `(dispositius, rutes_denegades)`. Els dispositius virtuals de
    `ydotool`/`uinput` s'exclouen per no llegir les nostres pròpies injeccions.
    """
    try:
        import evdev
        from evdev import ecodes
    except ImportError as exc:  # pragma: no cover - depèn de l'entorn
        raise RuntimeError(_EVDEV_INSTALL_HINT) from exc

    devices: list[object] = []
    denied: list[str] = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except PermissionError:
            denied.append(path)
            continue
        except OSError:
            continue

        try:
            keys = device.capabilities().get(ecodes.EV_KEY, [])
            identity = " ".join(
                filter(None, (
                    device.name,
                    getattr(device, "phys", ""),
                    getattr(device, "uniq", ""),
                ))
            ).lower()
            if (
                ecodes.KEY_A in keys
                and "ydotool" not in identity
                and "uinput" not in identity
            ):
                devices.append(device)
            else:
                device.close()
        except Exception:  # noqa: BLE001 - un dispositiu rar no ha de tombar res
            device.close()
    return devices, denied


@dataclass
class _Binding:
    modifiers: frozenset[str]
    key: str
    on_press: Callable[[], None]
    on_release: Callable[[], None] | None
    active: bool = False
    codes: frozenset[int] = frozenset()


class HotkeyManager:
    """Hotkeys globals per a X11 (`pynput`) i Wayland (`evdev`)."""

    def __init__(self, interval: float = 0.025) -> None:
        self.interval = interval
        self._bindings: list[_Binding] = []
        self._keyboard = None
        self._listener = None
        self._modifier_sets: dict[str, set[object]] = {}
        self._modifier_reverse: dict[object, str] = {}
        self._pressed_modifiers: set[str] = set()
        self._key_cache: dict[str, object] = {}
        self._started = False

        # Wayland / evdev
        self._ecodes = None
        self._devices: list[object] = []
        self._evdev_thread: threading.Thread | None = None
        self._evdev_stop: threading.Event | None = None
        self._evdev_reverse: dict[int, str] = {}

    def add(self, combo: str, on_press, on_release=None) -> None:  # noqa: ANN001
        parsed = parse(combo)
        self._bindings.append(
            _Binding(frozenset(parsed.modifiers), parsed.key, on_press, on_release)
        )

    def start(self) -> None:
        if self._started:
            return
        if _session_is_wayland():
            self._start_evdev()
        else:
            self._start_pynput()
        self._started = True

    def stop(self) -> None:
        listener, self._listener = self._listener, None
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                listener.join(timeout=1.0)
            except Exception:  # noqa: BLE001
                pass

        stop_event, self._evdev_stop = self._evdev_stop, None
        if stop_event is not None:
            stop_event.set()
        thread, self._evdev_thread = self._evdev_thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

        for device in list(self._devices):
            try:
                device.close()
            except Exception:  # noqa: BLE001
                pass
        self._devices.clear()

        global _active_manager
        if _active_manager is self:
            _active_manager = None

        self._started = False
        self._pressed_modifiers.clear()
        for binding in self._bindings:
            binding.active = False

    def modifiers_pressed(self) -> bool:
        return bool(self._pressed_modifiers)

    # ------------------------------------------------------------------ X11

    def _start_pynput(self) -> None:
        _require_x11("Hotkeys")
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise RuntimeError(
                "Falta `pynput`. Instal·la'l amb: pip install pynput"
            ) from exc

        self._keyboard = keyboard
        self._modifier_sets, self._modifier_reverse = _modifier_maps(keyboard)
        self._pressed_modifiers.clear()
        self._key_cache.clear()
        for binding in self._bindings:
            binding.active = False
            if binding.key in self._modifier_sets:
                continue
            try:
                self._target_key(binding.key)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(
                    f"La tecla {binding.key!r} no és compatible amb pynput: {exc}"
                ) from exc

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def _target_key(self, key_name: str):  # noqa: ANN202
        target = self._key_cache.get(key_name)
        if target is None:
            target = _to_pynput_key(self._keyboard, key_name)
            self._key_cache[key_name] = target
        return target

    def _key_matches(self, key, key_name: str) -> bool:  # noqa: ANN001
        if key_name in self._modifier_sets:
            return key in self._modifier_sets[key_name]
        try:
            target = self._target_key(key_name)
        except Exception:  # noqa: BLE001
            return False
        if key == target:
            return True
        keyboard = self._keyboard
        if isinstance(key, keyboard.KeyCode) and isinstance(target, keyboard.KeyCode):
            left, right = key.char, target.char
            return (
                left is not None
                and right is not None
                and left.lower() == right.lower()
            )
        return False

    def _on_press(self, key) -> None:  # noqa: ANN001
        modifier = self._modifier_reverse.get(key)
        if modifier is not None:
            self._pressed_modifiers.add(modifier)

        for binding in self._bindings:
            if binding.active:
                continue
            if (
                binding.modifiers <= self._pressed_modifiers
                and self._key_matches(key, binding.key)
            ):
                binding.active = True
                threading.Thread(target=binding.on_press, daemon=True).start()

    def _on_release(self, key) -> None:  # noqa: ANN001
        for binding in self._bindings:
            if binding.active and self._key_matches(key, binding.key):
                binding.active = False
                if binding.on_release is not None:
                    threading.Thread(target=binding.on_release, daemon=True).start()

        modifier = self._modifier_reverse.get(key)
        if modifier is not None:
            self._pressed_modifiers.discard(modifier)

    # -------------------------------------------------------------- Wayland

    def _start_evdev(self) -> None:
        try:
            from evdev import ecodes
        except ImportError as exc:
            raise RuntimeError(_EVDEV_INSTALL_HINT) from exc

        self._ecodes = ecodes
        modifier_sets = _evdev_modifier_sets(ecodes)
        self._evdev_reverse = {
            code: name for name, codes in modifier_sets.items() for code in codes
        }
        self._pressed_modifiers.clear()
        for binding in self._bindings:
            binding.active = False
            if binding.key in modifier_sets:
                binding.codes = frozenset(modifier_sets[binding.key])
                continue
            try:
                binding.codes = frozenset({_evdev_code(ecodes, binding.key)})
            except ValueError as exc:
                raise ValueError(
                    f"La tecla {binding.key!r} no és compatible amb evdev: {exc}"
                ) from exc

        devices, denied = _open_evdev_keyboards()
        if not devices:
            if denied:
                raise RuntimeError(_INPUT_PERMISSION_HINT)
            raise RuntimeError(
                "No s'ha trobat cap teclat llegible a /dev/input/event*. "
                "Comprova els permisos i que el paquet `evdev` funcioni."
            )

        self._devices = devices
        self._evdev_stop = threading.Event()
        self._evdev_thread = threading.Thread(
            target=self._evdev_loop, daemon=True,
        )
        global _active_manager
        _active_manager = self
        try:
            self._evdev_thread.start()
        except Exception:
            for device in self._devices:
                try:
                    device.close()
                except Exception:  # noqa: BLE001
                    pass
            self._devices.clear()
            self._evdev_thread = None
            self._evdev_stop = None
            if _active_manager is self:
                _active_manager = None
            raise

    def _evdev_loop(self) -> None:
        stop_event = self._evdev_stop
        if stop_event is None:
            return
        selector = selectors.DefaultSelector()
        try:
            for device in self._devices:
                try:
                    selector.register(device.fd, selectors.EVENT_READ, device)
                except Exception:  # noqa: BLE001 - el dispositiu pot haver marxat
                    continue
            while not stop_event.is_set():
                for key, _ in selector.select(timeout=0.2):
                    device = key.data
                    try:
                        events = list(device.read())
                    except OSError:
                        try:
                            selector.unregister(device.fd)
                        except Exception:  # noqa: BLE001
                            pass
                        continue
                    for event in events:
                        self._handle_evdev(event)
        finally:
            for device in self._devices:
                try:
                    selector.unregister(device.fd)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    device.close()
                except Exception:  # noqa: BLE001
                    pass
            self._devices.clear()
            selector.close()
            self._pressed_modifiers.clear()

    def _handle_evdev(self, event) -> None:  # noqa: ANN001
        ecodes = self._ecodes
        if ecodes is None or event.type != ecodes.EV_KEY:
            return
        if event.value not in (0, 1):
            return

        code = event.code
        modifier = self._evdev_reverse.get(code)

        if event.value == 1:
            if modifier is not None:
                self._pressed_modifiers.add(modifier)
            for binding in self._bindings:
                if binding.active:
                    continue
                if (
                    code in binding.codes
                    and binding.modifiers <= self._pressed_modifiers
                ):
                    binding.active = True
                    threading.Thread(
                        target=binding.on_press, daemon=True,
                    ).start()
            return

        for binding in self._bindings:
            if binding.active and code in binding.codes:
                binding.active = False
                if binding.on_release is not None:
                    threading.Thread(
                        target=binding.on_release, daemon=True,
                    ).start()
        if modifier is not None:
            self._pressed_modifiers.discard(modifier)


# Gestor actiu, perquè `modifiers_down()` pugui consultar l'estat d'evdev.
_active_manager: HotkeyManager | None = None


# ------------------------------------------------------------------- inserció


def _run_xdotool(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["xdotool", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Falta `xdotool`. Instal·la'l amb el gestor de paquets "
            "(per exemple: sudo apt install xdotool)."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("`xdotool` no ha respost a temps.") from exc

    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        if not detail:
            detail = f"codi de sortida {result.returncode}"
        raise RuntimeError(f"xdotool ha fallat: {detail}")
    return result


def _xdotool_key(keystroke: str, repeat: int = 1) -> None:
    args = ["key", "--clearmodifiers"]
    if repeat > 1:
        args += ["--repeat", str(repeat), "--delay", "2"]
    args.append(keystroke)
    _run_xdotool(args)


def foreground_window() -> int | None:
    """Retorna la finestra activa a X11; a Wayland no hi ha equivalent fiable."""
    if _session_is_wayland() or not os.environ.get("DISPLAY"):
        return None
    result = _run_xdotool(["getactivewindow"], check=False)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _focus_ok(expected_hwnd: int | None) -> bool:
    if expected_hwnd is None:
        return True
    current = foreground_window()
    # Si no podem consultar la finestra activa, no bloquegem el dictat.
    return current is None or current == expected_hwnd


def _type_chunk(text: str) -> None:
    if not text:
        return
    _run_xdotool(
        ["type", "--clearmodifiers", "--delay", "2", "--", text]
    )


def _x11_type_text(text: str, expected_hwnd: int | None = None) -> int:
    if not _focus_ok(expected_hwnd):
        raise InsertAborted(0)

    written = 0
    buffer: list[str] = []
    for char in text:
        if char in "\n\t":
            if buffer:
                if not _focus_ok(expected_hwnd):
                    raise InsertAborted(written)
                chunk = "".join(buffer)
                _type_chunk(chunk)
                written += len(chunk)
                buffer.clear()
            if not _focus_ok(expected_hwnd):
                raise InsertAborted(written)
            _xdotool_key("Return" if char == "\n" else "Tab")
            written += 1
        else:
            buffer.append(char)

    if buffer:
        if not _focus_ok(expected_hwnd):
            raise InsertAborted(written)
        chunk = "".join(buffer)
        _type_chunk(chunk)
        written += len(chunk)
    return len(text)


def _x11_paste_text(text: str, restore_clipboard: bool,
                    expected_hwnd: int | None = None) -> int:
    previous = _clipboard_get() if restore_clipboard else None
    if not _clipboard_set(text):
        raise RuntimeError(
            "No s'ha pogut escriure al porta-retalls. "
            "Instal·la `xclip` o `xsel` (per exemple: sudo apt install xclip)."
        )
    try:
        time.sleep(0.06)
        if not _focus_ok(expected_hwnd):
            raise InsertAborted(0)
        _xdotool_key("ctrl+v")
        time.sleep(0.30)
    finally:
        if restore_clipboard and previous is not None:
            _clipboard_set(previous)
    return len(text)


# --------------------------------------------------------- ydotool / wtype


def _run_checked(args: list[str], tool: str,
                 timeout: float = 30.0) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Falta `{tool}`.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"`{tool}` no ha respost a temps.") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if not detail:
            detail = f"codi de sortida {result.returncode}"
        lowered = detail.lower()
        if tool == "ydotool" and ("socket" in lowered or "connect" in lowered):
            detail += f" — {_YDOTOOLD_HINT}"
        elif tool == "ydotool" and (
            "uinput" in lowered or "permission denied" in lowered
        ):
            detail += (
                " — comprova que `ydotoold` tingui accés a /dev/uinput "
                "(grup `input` o una regla udev)."
            )
        raise RuntimeError(f"{tool} ha fallat: {detail}")
    return result


def _try_inject(ydotool_args: list[str], wtype_args: list[str],
                feature: str) -> None:
    """Prova `ydotool` i, si falla, `wtype`."""
    errors: list[str] = []

    ydotool = shutil.which("ydotool")
    if ydotool:
        try:
            _run_checked([ydotool, *ydotool_args], "ydotool")
            return
        except RuntimeError as exc:
            errors.append(str(exc))

    wtype = shutil.which("wtype")
    if wtype:
        try:
            _run_checked([wtype, *wtype_args], "wtype")
            return
        except RuntimeError as exc:
            errors.append(str(exc))

    if errors:
        raise RuntimeError(f"{feature}: " + " | ".join(errors))
    raise RuntimeError(f"{feature}: {_INJECTOR_INSTALL_HINT}")


def _wayland_type_chunk(text: str) -> None:
    if not text:
        return
    # `-d` és `--key-delay` a ydotool 1.x. Amb versions antigues l'opció no
    # existeix, així que es reintenta sense opcions abans de passar a wtype.
    errors: list[str] = []
    ydotool = shutil.which("ydotool")
    if ydotool:
        text_args = ["--", text] if text.startswith("-") else [text]
        for args in (["type", "-d", "2", *text_args], ["type", *text_args]):
            try:
                _run_checked([ydotool, *args], "ydotool")
                return
            except RuntimeError as exc:
                errors.append(str(exc))

    wtype = shutil.which("wtype")
    if wtype:
        wtype_args = ["--", text] if text.startswith("-") else [text]
        try:
            _run_checked([wtype, *wtype_args], "wtype")
            return
        except RuntimeError as exc:
            errors.append(str(exc))

    if errors:
        raise RuntimeError("Inserció: " + " | ".join(errors))
    raise RuntimeError(f"Inserció: {_INJECTOR_INSTALL_HINT}")


def _wayland_press(key_name: str) -> None:
    if key_name == "enter":
        _try_inject(
            ["key", "28:1", "28:0"],
            ["-k", "Return"],
            "Inserció",
        )
    elif key_name == "tab":
        _try_inject(
            ["key", "15:1", "15:0"],
            ["-k", "Tab"],
            "Inserció",
        )
    else:  # pragma: no cover - només s'usa internament
        raise ValueError(f"Tecla Wayland desconeguda: {key_name}")


def _wayland_type_text(text: str) -> int:
    buffer: list[str] = []
    for char in text:
        if char in "\n\t":
            if buffer:
                chunk = "".join(buffer)
                _wayland_type_chunk(chunk)
                buffer.clear()
            _wayland_press("enter" if char == "\n" else "tab")
        else:
            buffer.append(char)
    if buffer:
        _wayland_type_chunk("".join(buffer))
    return len(text)


def _wayland_send_ctrl_v() -> None:
    _try_inject(
        ["key", "29:1", "47:1", "47:0", "29:0"],
        ["-M", "ctrl", "-k", "v", "-m", "ctrl"],
        "Inserció",
    )


def _wayland_send_ctrl_z() -> None:
    _try_inject(
        ["key", "29:1", "44:1", "44:0", "29:0"],
        ["-M", "ctrl", "-k", "z", "-m", "ctrl"],
        "Desfer",
    )


def _wayland_send_backspaces(count: int) -> None:
    remaining = max(0, count)
    while remaining > 0:
        batch = min(remaining, 50)
        ydotool_args = ["key"]
        for _ in range(batch):
            ydotool_args += ["14:1", "14:0"]
        wtype_args = ["-k", "BackSpace"] * batch
        _try_inject(ydotool_args, wtype_args, "Desfer")
        remaining -= batch
        if remaining:
            time.sleep(0.002)


def _wl_clipboard_get() -> str | None:
    executable = shutil.which("wl-paste")
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--no-newline"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _wl_clipboard_set(text: str) -> bool:
    executable = shutil.which("wl-copy")
    if not executable:
        return False
    # `wl-copy` fa fork: el fill es queda servint el porta-retalls i hereta els
    # descriptors. Amb `capture_output=True` el pare no rep EOF fins que el fill
    # mor, i la crida es quedava penjada fins al timeout. Cal enviar la sortida
    # a /dev/null.
    try:
        result = subprocess.run(
            [executable],
            input=text,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _wayland_paste_text(text: str, restore_clipboard: bool) -> int:
    previous = _wl_clipboard_get() if restore_clipboard else None
    if not _wl_clipboard_set(text):
        raise RuntimeError(
            "No s'ha pogut escriure al porta-retalls. " + _CLIPBOARD_INSTALL_HINT
        )
    try:
        time.sleep(0.06)
        _wayland_send_ctrl_v()
        time.sleep(0.30)
    finally:
        if restore_clipboard and previous is not None:
            _wl_clipboard_set(previous)
    return len(text)


# --------------------------------------------------------------- API pública


def type_text(text: str, expected_hwnd: int | None = None) -> int:
    """Escriu text amb `xdotool` (X11) o `ydotool`/`wtype` (Wayland)."""
    if not text:
        return 0
    if _session_is_wayland():
        # Wayland no permet consultar la finestra activa de forma fiable.
        if not text.isascii():
            # ydotool només coneix el teclat US: s'atura en silenci al primer
            # accent (à, ç, ò...). El porta-retalls conserva tots els caràcters.
            return _wayland_paste_text(text, restore_clipboard=True)
        return _wayland_type_text(text)
    _require_x11("Inserció")
    return _x11_type_text(text, expected_hwnd)


def send_ctrl_v() -> None:
    if _session_is_wayland():
        _wayland_send_ctrl_v()
        return
    _require_x11("Inserció")
    _xdotool_key("ctrl+v")


def send_ctrl_z() -> None:
    if _session_is_wayland():
        _wayland_send_ctrl_z()
        return
    _require_x11("Desfer")
    _xdotool_key("ctrl+z")


def send_backspaces(count: int) -> None:
    if count <= 0:
        return
    if _session_is_wayland():
        _wayland_send_backspaces(count)
        return
    _require_x11("Desfer")
    _xdotool_key("BackSpace", repeat=count)


def key_is_down(vk: int) -> bool:
    # No s'utilitza a Linux; es manté per compatibilitat amb la interfície.
    return False


def modifiers_down() -> bool:
    """Indica si hi ha modificadors premuts.

    A Wayland ho sap gràcies al listener d'evdev. A X11 no cal perquè
    `xdotool key --clearmodifiers` ja neutralitza els modificadors.
    """
    if _session_is_wayland():
        manager = _active_manager
        return bool(manager and manager.modifiers_pressed())
    return False


def _clipboard_get() -> str | None:
    try:
        import pyperclip

        return pyperclip.paste()
    except Exception:  # noqa: BLE001
        return None


def _clipboard_set(text: str) -> bool:
    try:
        import pyperclip
    except ImportError:
        return False

    for _ in range(5):
        try:
            pyperclip.copy(text)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.05)
    return False


def paste_text(text: str, restore_clipboard: bool = True,
               expected_hwnd: int | None = None) -> int:
    """Enganxa text via porta-retalls + Ctrl+V."""
    if not text:
        return 0
    if _session_is_wayland():
        return _wayland_paste_text(text, restore_clipboard)
    _require_x11("Inserció")
    return _x11_paste_text(text, restore_clipboard, expected_hwnd)


# ------------------------------------------------------------------- instància

try:
    import fcntl
except ImportError:  # pragma: no cover - només passa si s'importa a Windows
    fcntl = None  # type: ignore[assignment]


class SingleInstance:
    """Bloqueig d'instància única amb `fcntl.flock`."""

    def __init__(self, name: str = "CustormWispeFlow") -> None:
        self.name = name
        self.handle = None
        self.already_running = False
        if fcntl is None:
            return

        safe_name = name.replace("\\", "_").replace("/", "_")
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        directory = Path(runtime_dir) if runtime_dir else Path(tempfile.gettempdir())
        self.path = directory / f"{safe_name}.lock"
        try:
            self.handle = self.path.open("a+")
        except OSError:
            self.path = Path(tempfile.gettempdir()) / f"{safe_name}.lock"
            try:
                self.handle = self.path.open("a+")
            except OSError:
                self.handle = None
                return

        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.already_running = True

    def close(self) -> None:
        if self.handle is None:
            return
        if fcntl is not None:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        self.handle.close()
        self.handle = None


# ------------------------------------------------------------------------ so

def beep(frequency: int, duration: int) -> None:
    """Reprodueix un to curt amb `sounddevice`."""
    try:
        import numpy as np
        import sounddevice as sd

        rate = 44100
        samples = max(1, int(rate * duration / 1000))
        timeline = np.linspace(
            0.0, duration / 1000.0, samples, endpoint=False, dtype=np.float32
        )
        wave = 0.18 * np.sin(2.0 * np.pi * frequency * timeline)
        wave = wave.astype(np.float32)

        fade = min(128, samples // 4)
        if fade > 0:
            envelope = np.ones(samples, dtype=np.float32)
            envelope[:fade] = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            envelope[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
            wave *= envelope

        sd.play(wave, rate)
        sd.wait()
    except Exception:  # noqa: BLE001 - el so no ha de tombar l'aplicació
        log.debug("no s'ha pogut reproduir el to", exc_info=True)
