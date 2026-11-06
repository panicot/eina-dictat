"""Inserció de text (façana multiplataforma).

La implementació concreta viu a `app.backends.windows` o
`app.backends.linux`. Aquest mòdul manté l'API que fa servir la resta de
l'aplicació.
"""

from __future__ import annotations

from app.backends import backend

InsertAborted = backend.InsertAborted

# Exposat per als tests i per a inspecció.
_backend = backend


def foreground_window() -> int | None:
    return backend.foreground_window()


def type_text(text: str, expected_hwnd: int | None = None) -> int:
    return backend.type_text(text, expected_hwnd)


def paste_text(text: str, restore_clipboard: bool = True,
               expected_hwnd: int | None = None) -> int:
    return backend.paste_text(text, restore_clipboard, expected_hwnd)


def send_ctrl_v() -> None:
    backend.send_ctrl_v()


def send_ctrl_z() -> None:
    backend.send_ctrl_z()


def send_backspaces(count: int) -> None:
    backend.send_backspaces(count)


def key_is_down(vk: int) -> bool:
    return backend.key_is_down(vk)


def modifiers_down() -> bool:
    return backend.modifiers_down()


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
