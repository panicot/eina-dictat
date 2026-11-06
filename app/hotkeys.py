"""Hotkeys globals (façana multiplataforma).

La implementació concreta viu a `app.backends.windows` o
`app.backends.linux`.
"""

from __future__ import annotations

from app.backends import backend

MODIFIERS = getattr(backend, "MODIFIERS", {})
KEYS = getattr(backend, "KEYS", {})

parse = backend.parse
HotkeyManager = backend.HotkeyManager

__all__ = ["MODIFIERS", "KEYS", "parse", "HotkeyManager"]
