"""Utilitats de l'historial de dictades."""

from __future__ import annotations

from pathlib import Path


def trim_history(path: Path, max_lines: int) -> int:
    """Deixa nomes les ultimes `max_lines` linies. Retorna quantes n'ha tret.

    `max_lines <= 0` vol dir sense limit.
    """
    if max_lines <= 0 or not path.exists():
        return 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    if len(lines) <= max_lines:
        return 0
    removed = len(lines) - max_lines
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    tmp.replace(path)
    return removed
