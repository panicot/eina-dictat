"""Senyals sonors amb significat.

Cada esdeveniment te un patro de tons propi, de manera que es pot saber l'estat
sense mirar la pantalla. Els tons s'encuen en un sol fil perque el reproductor
de plataforma es bloquejant: abans cada beep obria un fil i els patrons llargs
se solapaven.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Callable

from app.backends import backend

Tone = tuple[int, int]  # (frequencia Hz, duracio ms)
Player = Callable[[int, int], None]


class Event(str, Enum):
    LISTENING = "listening"
    PROCESSING = "processing"
    DONE = "done"
    UNDONE = "undone"
    ERROR = "error"
    NO_SPEECH = "no_speech"
    BUSY = "busy"
    PUNCT_ON = "punct_on"
    PUNCT_OFF = "punct_off"
    SPELL_ON = "spell_on"
    SPELL_OFF = "spell_off"
    MODE_NORMAL = "mode_normal"
    LANG_CA = "lang_ca"
    LANG_ES = "lang_es"
    LANG_EN = "lang_en"


# Patrons pensats per ser distinguibles sense mirar: ascendents = activar,
# descendents = desactivar; un sol to = estat puntual.
PATTERNS: dict[Event, tuple[Tone, ...]] = {
    Event.LISTENING: ((880, 60),),
    Event.PROCESSING: ((660, 60),),
    Event.DONE: ((990, 60),),
    Event.UNDONE: ((990, 50), (990, 50)),
    Event.ERROR: ((300, 120), (220, 160)),
    Event.NO_SPEECH: ((300, 100),),
    Event.BUSY: ((300, 100), (300, 100)),
    Event.PUNCT_ON: ((700, 55), (900, 55)),
    Event.PUNCT_OFF: ((900, 55), (700, 55)),
    Event.SPELL_ON: ((600, 55), (600, 55), (900, 60)),
    Event.SPELL_OFF: ((900, 60), (600, 55), (600, 55)),
    Event.MODE_NORMAL: ((900, 50), (700, 50), (500, 70)),
    Event.LANG_CA: ((520, 45),),
    Event.LANG_ES: ((520, 45), (520, 45)),
    Event.LANG_EN: ((520, 45), (520, 45), (520, 45)),
}

LANGUAGE_EVENTS = {
    "ca": Event.LANG_CA,
    "es": Event.LANG_ES,
    "en": Event.LANG_EN,
}


def pattern_for(event: Event) -> tuple[Tone, ...]:
    return PATTERNS[event]


def _platform_beep(frequency: int, duration: int) -> None:
    backend.beep(frequency, duration)


class Feedback:
    """Cua de tons en un sol fil.

    `player` es injectable per poder provar els patrons sense fer soroll.
    """

    def __init__(self, enabled: bool = True,
                 player: Player | None = None) -> None:
        self.enabled = enabled
        self._player = player or _platform_beep
        self._events: deque[Event] = deque()
        self._cond = threading.Condition()
        self._running = True
        self._playing = False
        self._thread: threading.Thread | None = None

    def play(self, event: Event) -> None:
        if not self.enabled or not self._running:
            return
        with self._cond:
            if self._thread is None:
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()
            self._events.append(event)
            self._cond.notify()

    def _worker(self) -> None:
        while True:
            with self._cond:
                while not self._events and self._running:
                    self._cond.wait()
                if not self._events:
                    return
                event = self._events.popleft()
                self._playing = True
            try:
                for frequency, duration in pattern_for(event):
                    try:
                        self._player(frequency, duration)
                    except Exception:  # noqa: BLE001 - el so no ha de tombar res
                        break
            finally:
                with self._cond:
                    self._playing = False
                    self._cond.notify_all()

    def wait_idle(self, timeout: float = 2.0) -> bool:
        """Espera que no quedi cap to per reproduir. Retorna False si expira."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._events or self._playing:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def close(self) -> None:
        with self._cond:
            self._running = False
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
