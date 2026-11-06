#!/usr/bin/env python3
"""Proves del backend Linux sense necessitat d'una sessió gràfica.

Funciona a Windows i a Linux: simula `pynput`, `evdev`, `xdotool`, `ydotool`,
`wtype` i `wl-clipboard` amb mocks.

Us:
  python selftest_linux.py
"""

from __future__ import annotations

import os
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.backends import linux as backend  # noqa: E402

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    suffix = f"  ({detail})" if detail else ""
    print(f"  {label}: {'OK' if ok else 'FALLA'}{suffix}")


def test_parse() -> None:
    print("Hotkeys:")
    parsed = backend.parse("ctrl+shift+1")
    check("modificadors", parsed.modifiers == ("ctrl", "shift"), str(parsed))
    check("tecla", parsed.key == "1", str(parsed))
    check("win -> super", backend.parse("win+space").modifiers == ("super",))
    check("return -> enter", backend.parse("return").key == "enter")
    check("f8", backend.parse("F8").key == "f8")
    try:
        backend.parse("ctrl+noexisteix")
        check("tecla desconeguda", False)
    except ValueError:
        check("tecla desconeguda", True)


def test_session() -> None:
    print("Sessió:")
    names = ("CWF_BACKEND", "XDG_SESSION_TYPE", "WAYLAND_DISPLAY")
    saved = {name: os.environ.get(name) for name in names}
    try:
        os.environ["CWF_BACKEND"] = "x11"
        check("override x11", not backend._session_is_wayland())
        os.environ["CWF_BACKEND"] = "wayland"
        check("override wayland", backend._session_is_wayland())

        os.environ.pop("CWF_BACKEND", None)
        os.environ["XDG_SESSION_TYPE"] = "x11"
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        check("x11 té prioritat", not backend._session_is_wayland())

        os.environ["XDG_SESSION_TYPE"] = "wayland"
        check("wayland", backend._session_is_wayland())

        os.environ.pop("XDG_SESSION_TYPE", None)
        check("WAYLAND_DISPLAY", backend._session_is_wayland())
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_x11() -> None:
    print("X11:")
    calls: list[tuple[str, ...]] = []
    original = {
        "session": backend._session_is_wayland,
        "require": backend._require_x11,
        "run": backend._run_xdotool,
        "foreground": backend.foreground_window,
        "clip_get": backend._clipboard_get,
        "clip_set": backend._clipboard_set,
    }

    class Result:
        returncode = 0
        stdout = "123"
        stderr = ""

    backend._session_is_wayland = lambda: False
    backend._require_x11 = lambda feature: None
    backend._run_xdotool = lambda args, check=True: calls.append(tuple(args)) or Result()
    backend.foreground_window = lambda: 123
    try:
        check("type", backend.type_text("hola\nhi\t!", expected_hwnd=123) == 9)
        check("type envia blocs", calls[0] == (
            "type", "--clearmodifiers", "--delay", "2", "--", "hola",
        ), str(calls[0]))
        check("type envia Return", calls[1] == (
            "key", "--clearmodifiers", "Return",
        ))
        check("type envia Tab", calls[3] == (
            "key", "--clearmodifiers", "Tab",
        ))

        calls.clear()
        backend.send_ctrl_v()
        backend.send_ctrl_z()
        backend.send_backspaces(3)
        check("ctrl+v", calls[0] == ("key", "--clearmodifiers", "ctrl+v"))
        check("ctrl+z", calls[1] == ("key", "--clearmodifiers", "ctrl+z"))
        check("retrocessos", calls[2] == (
            "key", "--clearmodifiers", "--repeat", "3", "--delay", "2",
            "BackSpace",
        ), str(calls[2]))

        clipboard: list[str] = []
        backend._clipboard_get = lambda: "old"
        backend._clipboard_set = lambda text: clipboard.append(text) or True
        check("paste", backend.paste_text("hola", expected_hwnd=123) == 4)
        check("paste restaura", clipboard == ["hola", "old"], str(clipboard))

        backend.foreground_window = lambda: 999
        try:
            backend.type_text("abc", expected_hwnd=123)
            check("guard de focus", False)
        except backend.InsertAborted as exc:
            check("guard de focus", exc.chars_written == 0)
    finally:
        backend._session_is_wayland = original["session"]
        backend._require_x11 = original["require"]
        backend._run_xdotool = original["run"]
        backend.foreground_window = original["foreground"]
        backend._clipboard_get = original["clip_get"]
        backend._clipboard_set = original["clip_set"]


def test_wayland() -> None:
    print("Wayland:")
    original = {
        "session": backend._session_is_wayland,
        "chunk": backend._wayland_type_chunk,
        "press": backend._wayland_press,
        "inject": backend._try_inject,
        "clip_get": backend._wl_clipboard_get,
        "clip_set": backend._wl_clipboard_set,
        "ctrl_v": backend._wayland_send_ctrl_v,
    }
    backend._session_is_wayland = lambda: True
    chunks: list[str] = []
    keys: list[str] = []
    calls: list[tuple[tuple[str, ...], tuple[str, ...], str]] = []
    backend._wayland_type_chunk = lambda text: chunks.append(text)
    backend._wayland_press = lambda key: keys.append(key)
    backend._try_inject = (
        lambda yd, wt, feature: calls.append((tuple(yd), tuple(wt), feature))
    )
    try:
        check("type", backend.type_text("hola\nhi\t!") == 9)
        check("type blocs", chunks == ["hola", "hi", "!"], str(chunks))
        check("type Return/Tab", keys == ["enter", "tab"], str(keys))

        calls.clear()
        backend.send_ctrl_v()
        backend.send_ctrl_z()
        backend.send_backspaces(3)
        check("ctrl+v", calls[0][0] == ("key", "29:1", "47:1", "47:0", "29:0"))
        check("ctrl+z", calls[1][0] == ("key", "29:1", "44:1", "44:0", "29:0"))
        check("retrocessos", calls[2][0] == (
            "key", "14:1", "14:0", "14:1", "14:0", "14:1", "14:0",
        ))
        check("wtype alternatiu", calls[2][1] == (
            "-k", "BackSpace", "-k", "BackSpace", "-k", "BackSpace",
        ))

        clipboard: list[str] = []
        backend._wl_clipboard_get = lambda: "old"
        backend._wl_clipboard_set = lambda text: clipboard.append(text) or True
        backend._wayland_send_ctrl_v = lambda: clipboard.append("ctrl_v")
        check("paste", backend.paste_text("hola") == 4)
        check("paste restaura", clipboard == ["hola", "ctrl_v", "old"],
              str(clipboard))
    finally:
        backend._session_is_wayland = original["session"]
        backend._wayland_type_chunk = original["chunk"]
        backend._wayland_press = original["press"]
        backend._try_inject = original["inject"]
        backend._wl_clipboard_get = original["clip_get"]
        backend._wl_clipboard_set = original["clip_set"]
        backend._wayland_send_ctrl_v = original["ctrl_v"]


def test_type_chunk() -> None:
    print("ydotool type:")
    original = {
        "which": backend.shutil.which,
        "run": backend._run_checked,
    }
    backend.shutil.which = lambda name: {
        "ydotool": "/usr/bin/ydotool",
        "wtype": "/usr/bin/wtype",
    }.get(name)

    attempts: list[tuple[str, ...]] = []

    def run(args, tool, timeout=30.0):  # noqa: ANN001
        attempts.append(tuple(args))
        if len(attempts) == 1:
            raise RuntimeError("ydotool ha fallat: opció desconeguda")

    backend._run_checked = run
    try:
        backend._wayland_type_chunk("hola")
        check("reintenta sense -d", attempts[-1] == (
            "/usr/bin/ydotool", "type", "hola",
        ), str(attempts[-1]))

        attempts.clear()

        def run_all(args, tool, timeout=30.0):  # noqa: ANN001
            attempts.append(tuple(args))
            if tool == "ydotool":
                raise RuntimeError("ydotool ha fallat")

        backend._run_checked = run_all
        backend._wayland_type_chunk("-hola")
        check("text amb guió i wtype", attempts[-1] == (
            "/usr/bin/wtype", "--", "-hola",
        ), str(attempts[-1]))
    finally:
        backend.shutil.which = original["which"]
        backend._run_checked = original["run"]


def test_injector_fallback() -> None:
    print("Injector:")
    original = {
        "which": backend.shutil.which,
        "run": backend._run_checked,
    }
    calls: list[tuple[str, ...]] = []

    backend.shutil.which = lambda name: {
        "ydotool": "/usr/bin/ydotool",
        "wtype": "/usr/bin/wtype",
    }.get(name)

    def run(args, tool, timeout=30.0):  # noqa: ANN001
        if tool == "ydotool":
            raise RuntimeError("ydotool ha fallat: socket")
        calls.append(tuple(args))

    backend._run_checked = run
    try:
        backend._try_inject(["type", "x"], ["--", "x"], "Inserció")
        check("ydotool -> wtype", calls == [
            ("/usr/bin/wtype", "--", "x"),
        ], str(calls))

        backend.shutil.which = lambda name: None
        try:
            backend._try_inject(["type", "x"], ["--", "x"], "Inserció")
            check("sense injector", False)
        except RuntimeError as exc:
            check("sense injector", "ydotool" in str(exc) and "wtype" in str(exc))
    finally:
        backend.shutil.which = original["which"]
        backend._run_checked = original["run"]


def test_evdev() -> None:
    print("evdev:")
    original = {
        "session": backend._session_is_wayland,
        "open": backend._open_evdev_keyboards,
        "loop": backend.HotkeyManager._evdev_loop,
    }
    had_evdev = "evdev" in sys.modules
    old_evdev = sys.modules.get("evdev")

    ecodes = types.SimpleNamespace(
        EV_KEY=1,
        KEY_A=30, KEY_1=2, KEY_F8=66,
        KEY_LEFTCTRL=29, KEY_RIGHTCTRL=97,
        KEY_LEFTALT=56, KEY_RIGHTALT=100,
        KEY_LEFTSHIFT=42, KEY_RIGHTSHIFT=54,
        KEY_LEFTMETA=125, KEY_RIGHTMETA=126,
        KEY_SPACE=57,
    )
    fake_evdev = types.ModuleType("evdev")
    fake_evdev.ecodes = ecodes
    sys.modules["evdev"] = fake_evdev

    class Device:
        fd = 12345

        def read(self):  # noqa: ANN201
            return []

        def close(self) -> None:
            pass

    class Event:
        def __init__(self, code: int, value: int) -> None:
            self.type = ecodes.EV_KEY
            self.code = code
            self.value = value

    backend._session_is_wayland = lambda: True
    backend._open_evdev_keyboards = lambda: ([Device()], [])
    backend.HotkeyManager._evdev_loop = lambda self: None

    calls: list[str] = []
    manager = backend.HotkeyManager()
    manager.add("ctrl+shift+1",
                lambda: calls.append("press"),
                lambda: calls.append("release"))
    manager.add("super",
                lambda: calls.append("super"), None)
    try:
        manager.start()
        check("arrenca", manager._started)
        manager._handle_evdev(Event(ecodes.KEY_LEFTCTRL, 1))
        manager._handle_evdev(Event(ecodes.KEY_LEFTSHIFT, 1))
        manager._handle_evdev(Event(ecodes.KEY_1, 1))
        check("hotkey premuda", calls == ["press"], str(calls))
        check("modificadors actius", backend.modifiers_down())
        manager._handle_evdev(Event(ecodes.KEY_1, 0))
        check("hotkey alliberada", calls == ["press", "release"], str(calls))
        manager._handle_evdev(Event(ecodes.KEY_LEFTSHIFT, 0))
        manager._handle_evdev(Event(ecodes.KEY_LEFTCTRL, 0))
        check("modificadors alliberats", not backend.modifiers_down())
        manager._handle_evdev(Event(ecodes.KEY_LEFTMETA, 1))
        manager._handle_evdev(Event(ecodes.KEY_LEFTMETA, 0))
        check("binding de modificador", calls[-1] == "super", str(calls))
    finally:
        manager.stop()
        backend._session_is_wayland = original["session"]
        backend._open_evdev_keyboards = original["open"]
        backend.HotkeyManager._evdev_loop = original["loop"]
        if had_evdev:
            sys.modules["evdev"] = old_evdev
        else:
            sys.modules.pop("evdev", None)

    sys.modules["evdev"] = fake_evdev
    backend._session_is_wayland = lambda: True
    backend._open_evdev_keyboards = lambda: ([], ["/dev/input/event0"])
    try:
        backend.HotkeyManager().start()
        check("permisos", False)
    except RuntimeError as exc:
        check("permisos", "grup `input`" in str(exc), str(exc))
    finally:
        backend._session_is_wayland = original["session"]
        backend._open_evdev_keyboards = original["open"]
        if had_evdev:
            sys.modules["evdev"] = old_evdev
        else:
            sys.modules.pop("evdev", None)


def test_wl_clipboard() -> None:
    print("wl-clipboard:")
    original = {
        "which": backend.shutil.which,
        "run": backend.subprocess.run,
    }
    backend.shutil.which = lambda name: {
        "wl-copy": "/usr/bin/wl-copy",
    }.get(name)

    captured: dict[str, object] = {}

    class Result:
        returncode = 0

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        captured["args"] = tuple(args)
        captured["kwargs"] = kwargs
        return Result()

    backend.subprocess.run = fake_run
    try:
        check("wl-copy", backend._wl_clipboard_set("hola") is True)
        kwargs = captured["kwargs"]
        check(
            "sortida a /dev/null",
            kwargs.get("stdout") is backend.subprocess.DEVNULL
            and kwargs.get("stderr") is backend.subprocess.DEVNULL,
            "wl-copy fa fork i penja capture_output",
        )
        check("text per stdin", kwargs.get("input") == "hola")
        check("executable", captured["args"] == ("/usr/bin/wl-copy",))

        def failing_run(args, **kwargs):  # noqa: ANN001, ANN003
            raise backend.subprocess.TimeoutExpired("wl-copy", 5)

        backend.subprocess.run = failing_run
        check("timeout -> False", backend._wl_clipboard_set("hola") is False)
    finally:
        backend.shutil.which = original["which"]
        backend.subprocess.run = original["run"]


def main() -> int:
    test_parse()
    test_session()
    test_x11()
    test_wayland()
    test_type_chunk()
    test_wl_clipboard()
    test_injector_fallback()
    test_evdev()
    print()
    print("TOT OK" if failures == 0 else f"{failures} FALLES")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
