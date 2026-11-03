"""Bloqueig d'instancia unica amb un mutex de Windows.

El mutex l'allibera el sistema quan el proces mor, tambe si peta, cosa que un
fitxer de PID no garanteix. Es fa servir `Local\\` (nomes la sessio actual) per
no barallar-se amb altres usuaris de la mateixa maquina.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183

if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (
        wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR,
    )
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
else:  # pragma: no cover - el projecte es Windows, pero no ha de petar en proves
    kernel32 = None


class SingleInstance:
    def __init__(self, name: str = r"Local\CustormWispeFlow") -> None:
        self.name = name
        self.handle = None
        self.already_running = False
        if kernel32 is None:
            return
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
