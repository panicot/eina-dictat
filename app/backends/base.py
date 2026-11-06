"""Interfícies compartides entre els backends de plataforma."""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


class InsertAborted(RuntimeError):
    """La finestra en primer pla ha canviat durant la inserció."""

    def __init__(self, chars_written: int = 0) -> None:
        super().__init__("La finestra activa ha canviat durant la insercio.")
        self.chars_written = chars_written


@runtime_checkable
class HotkeyManagerProtocol(Protocol):
    def add(
        self,
        combo: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None] | None = None,
    ) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


@runtime_checkable
class SingleInstanceProtocol(Protocol):
    already_running: bool

    def close(self) -> None: ...
