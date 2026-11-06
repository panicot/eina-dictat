"""Selecció del backend de plataforma."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from . import windows as backend
else:
    from . import linux as backend

__all__ = ["backend"]
