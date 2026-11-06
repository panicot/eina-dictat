"""Bloqueig d'instància única (façana multiplataforma).

Windows fa servir un mutex; Linux, un `fcntl.flock` sobre un fitxer de
`XDG_RUNTIME_DIR` (o el directori temporal).
"""

from __future__ import annotations

from app.backends import backend

SingleInstance = backend.SingleInstance

__all__ = ["SingleInstance"]
