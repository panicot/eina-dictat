"""Genera mostres amb les frases reals de l'usuari i les prova amb el pipeline complet."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"

from make_samples import mp3_to_wav  # noqa: E402
from app.config import load  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.textmodes import TextModes  # noqa: E402

# Frases exactes que l'usuari ha dictat de veritat (segons history.jsonl).
CASES = [
    ("real_url", "La sigla és u erre ele, i el codi és ce efa efa."),
    ("real_cmd", "Signes de puntuació. Necessito un arreglament, punt."),
    ("real_cmd2", "Activa signes de puntuació. Escriu exemple punt com."),
    ("real_single", "Escriu la lletra essa."),
    ("real_normal", "Aquesta és una frase normal per comprovar que no es trenca."),
]


async def synth(name: str, text: str) -> Path:
    import edge_tts

    mp3 = SAMPLES / f"_{name}.mp3"
    await edge_tts.Communicate(text, "ca-ES-JoanaNeural").save(str(mp3))
    wav = SAMPLES / f"{name}.wav"
    mp3_to_wav(mp3, wav)
    mp3.unlink()
    return wav


def main() -> int:
    cfg = load()
    engine = Engine(cfg)
    for name, text in CASES:
        wav = SAMPLES / f"{name}.wav"
        print(f"\n=== {name} ===")
        print(f"ref : {text}")
        if not wav.exists():
            print("  (sense wav)")
            continue
        raw, _ = engine.transcribe_file(wav, "ca")
        modes = TextModes(cfg)
        out = modes.transform(raw)
        print(f"raw : {raw}")
        print(f"out : {out}")
        print(f"      events={modes.events} punct={modes.punctuation_mode} spell={modes.spelling_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
