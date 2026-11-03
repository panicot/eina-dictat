"""Estat unic de l'aplicacio i format de la linia d'estat.

Abans l'estat estava repartit entre `busy`, `recorder.is_recording` i els
booleans dels modes; aixo feia que el terminal i els senyals no sempre
coincidissin. Ara tot passa per aixo.
"""

from __future__ import annotations

from enum import Enum


class State(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


LABELS = {
    State.IDLE: "IDLE",
    State.LISTENING: "ESCOLTANT",
    State.TRANSCRIBING: "TRANSCRIBUINT",
    State.ERROR: "ERROR",
}


def modes_label(punctuation: bool, spelling: bool) -> str:
    active = []
    if punctuation:
        active.append("PUNCT")
    if spelling:
        active.append("LLETRES")
    return "+".join(active) if active else "cap"


def status_line(state: State, language: str, punctuation: bool,
                spelling: bool) -> str:
    return (f"[estat] {LABELS[state]} · {language} · "
            f"modes: {modes_label(punctuation, spelling)}")
