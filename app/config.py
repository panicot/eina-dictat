"""Carrega i valida la configuracio de l'aplicacio."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config.toml"

DEFAULT_TOML = """\
# CustormWispeFlow - configuracio
hotkey = "f8"            # tecla per comencar/aturar (o mantenir, si mode = "hold")
                         # alternatives sense conflictes: "pause", "ctrl+shift+space"
undo_hotkey = "f9"       # desfer l'ultima insercio (nomes si la finestra es la mateixa)
mode = "toggle"          # "toggle" o "hold"
language = "ca"          # idioma inicial: ca, es, en

threads = 4              # fils de CPU per a Whisper
compute_type = "int8"    # int8 es el mes rapid en CPU
beam_size = 1            # 1 = mes rapid
vad = true               # retalla silenci abans de transcriure
max_seconds = 60.0       # durada maxima d'una dictada

insert_mode = "auto"     # "type" (SendInput), "paste" (porta-retalls) o "auto"
paste_threshold = 120    # amb "auto", a partir de quants caracters fer servir el porta-retalls
restore_clipboard = true # restaura el contingut anterior del porta-retalls
beeps = true             # senyals sonors d'inici/final
history_max_lines = 2000 # retalla history.jsonl en arrencar; 0 = sense limit
theme = "dark"           # "dark" o "light"
# device = "Micròfon (USB PnP Audio Device)"   # nom o index; buit = per defecte

# Modes de veu
spelling_auto = true     # detecta sigles: "u erre ele" -> "URL"
spelling_uppercase = true
spelling_separator = ""  # separador entre lletres; "" = cap

[models]
ca = "Jarbas/faster-whisper-base-ca-cv13"
es = "base"
en = "base"

[initial_prompts]
ca = "Transcripció en català amb puntuació i majúscules correctes. Ordres de veu: signes de puntuació, lletra a lletra, mode normal. Noms de lletra: a, be, ce, de, e, efa, ge, hac, i, jota, ca, ela, ema, ena, o, pe, cu, erra, essa, te, u, ve, xeix, zeta. També es diu erre, ele."
es = "Transcripción en español con puntuación y mayúsculas correctas. Órdenes: signos de puntuación, letra a letra, modo normal."
en = "English transcription with correct punctuation and capitalization. Commands: punctuation mode, spell mode, normal mode."

[dictionary]
# Substitucions despres de transcriure (sense distingir majuscules).
# "addictació" = "dictació"
"""


@dataclass
class Config:
    hotkey: str = "f8"
    undo_hotkey: str = "f9"
    mode: str = "toggle"
    language: str = "ca"
    threads: int = 4
    compute_type: str = "int8"
    beam_size: int = 1
    vad: bool = True
    max_seconds: float = 60.0
    insert_mode: str = "auto"
    paste_threshold: int = 120
    restore_clipboard: bool = True
    beeps: bool = True
    history_max_lines: int = 2000
    theme: str = "dark"
    device: str | None = None
    spelling_auto: bool = True
    spelling_uppercase: bool = True
    spelling_separator: str = ""

    models: dict[str, str] = field(default_factory=lambda: {
        "ca": "Jarbas/faster-whisper-base-ca-cv13",
        "es": "base",
        "en": "base",
    })
    initial_prompts: dict[str, str] = field(default_factory=lambda: {
        "ca": ("Transcripció en català amb puntuació i majúscules correctes. "
               "Ordres de veu: signes de puntuació, lletra a lletra, mode normal. "
               "Noms de lletra: a, be, ce, de, e, efa, ge, hac, i, jota, ca, ela, "
               "ema, ena, o, pe, cu, erra, essa, te, u, ve, xeix, zeta. "
               "També es diu erre, ele."),
        "es": ("Transcripción en español con puntuación y mayúsculas correctas. "
               "Órdenes: signos de puntuación, letra a letra, modo normal."),
        "en": ("English transcription with correct punctuation and capitalization. "
               "Commands: punctuation mode, spell mode, normal mode."),
    })
    dictionary: dict[str, str] = field(default_factory=dict)

    def model_for(self, language: str) -> str:
        return self.models.get(language, self.models.get("ca", "base"))

    def prompt_for(self, language: str) -> str | None:
        return self.initial_prompts.get(language) or None


def load(path: Path | None = None) -> Config:
    path = path or DEFAULT_PATH
    if not path.exists():
        path.write_text(DEFAULT_TOML, encoding="utf-8")

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = Config()

    for f in fields(cfg):
        if f.name in data:
            value = data[f.name]
            if isinstance(getattr(cfg, f.name), dict):
                merged = dict(getattr(cfg, f.name))
                merged.update(value)
                value = merged
            setattr(cfg, f.name, value)

    if cfg.language not in cfg.models:
        raise SystemExit(f"Idioma desconegut a config.toml: {cfg.language!r}")
    if cfg.mode not in {"toggle", "hold"}:
        raise SystemExit("mode ha de ser 'toggle' o 'hold'")
    if cfg.insert_mode not in {"type", "paste", "auto"}:
        raise SystemExit("insert_mode ha de ser 'type', 'paste' o 'auto'")
    if cfg.theme not in {"dark", "light"}:
        cfg.theme = "dark"
    return cfg
