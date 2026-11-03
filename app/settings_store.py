"""Lectura i escriptura de `config.toml` preservant comentaris i format.

`tomllib` només llegeix; per escriure fem servir `tomlkit`, que manté els
comentaris i l'ordre de les claus. Així la configuració continua sent llegible
i editable a mà encara que es canviï des de la interfície.
"""

from __future__ import annotations

from pathlib import Path

import tomlkit

from app.config import DEFAULT_PATH, Config, load

SCALAR_FIELDS = (
    "hotkey",
    "undo_hotkey",
    "mode",
    "language",
    "threads",
    "compute_type",
    "beam_size",
    "vad",
    "max_seconds",
    "insert_mode",
    "paste_threshold",
    "restore_clipboard",
    "beeps",
    "history_max_lines",
    "theme",
    "spelling_auto",
    "spelling_uppercase",
    "spelling_separator",
)


def save(cfg: Config, path: Path | None = None) -> None:
    """Escriu els camps editables de `cfg` a `config.toml`."""
    path = path or DEFAULT_PATH
    if path.exists():
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()

    for name in SCALAR_FIELDS:
        doc[name] = getattr(cfg, name)

    if cfg.device:
        doc["device"] = cfg.device
    else:
        doc.pop("device", None)

    models = doc.get("models")
    if models is None:
        models = tomlkit.table()
        doc["models"] = models
    for language in ("ca", "es", "en"):
        models[language] = cfg.models.get(language, "base")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def reload(path: Path | None = None) -> Config:
    return load(path)
