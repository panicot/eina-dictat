#!/usr/bin/env python3
"""Genera mostres d'audio de prova en catala, castella i angles amb edge-tts.

Cada mostra queda com a WAV 16 kHz mono a samples/ amb un .txt de referencia
al costat, perque bench.py pugui calcular el WER.

Us:
  python make_samples.py
  python make_samples.py --force
  python make_samples.py --only ca
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import wave
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"

SAMPLES_SPEC = [
    {
        "name": "ca_01",
        "lang": "ca",
        "voice": "ca-ES-JoanaNeural",
        "text": "Hola, això és una prova de dictació en català. Vull comprovar la latència "
                "i la qualitat de la transcripció amb el model local.",
    },
    {
        "name": "ca_02",
        "lang": "ca",
        "voice": "ca-ES-EnricNeural",
        "text": "Demà a les nou del matí hem de revisar el pressupost amb l'Anna i el Jordi, "
                "i després enviar-lo al client.",
    },
    {
        "name": "ca_03",
        "lang": "ca",
        "voice": "ca-ES-JoanaNeural",
        "text": "Obre el navegador i ves a example punt com barra documents per descarregar l'informe.",
    },
    {
        "name": "ca_04",
        "lang": "ca",
        "voice": "ca-ES-JoanaNeural",
        "text": "La sigla és u erre ele i el codi és ce efa efa.",
    },
    {
        "name": "ca_05",
        "lang": "ca",
        "voice": "ca-ES-EnricNeural",
        "text": "Signes de puntuació. Escriu example punt com barra documents i després punt i coma.",
    },
    {
        "name": "ca_06",
        "lang": "ca",
        "voice": "ca-ES-JoanaNeural",
        "text": "Lletra a lletra: a be ce, de, e, efa.",
    },
    {
        "name": "es_01",
        "lang": "es",
        "voice": "es-ES-ElviraNeural",
        "text": "Hola, esta es una prueba de dictado en español para medir la latencia "
                "y la precisión del sistema.",
    },
    {
        "name": "en_01",
        "lang": "en",
        "voice": "en-US-AriaNeural",
        "text": "Hello, this is an English dictation test to measure the latency "
                "and accuracy of the local model.",
    },
]


def mp3_to_wav(src: Path, dst: Path, rate: int = 16000) -> None:
    import av
    import numpy as np

    chunks: list[np.ndarray] = []
    with av.open(str(src)) as container:
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))

    data = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.astype(np.int16).tobytes())


async def synth(spec: dict, tmp: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(spec["text"], spec["voice"])
    await communicate.save(str(tmp))


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera mostres de prova amb TTS")
    parser.add_argument("--only", choices=["ca", "es", "en"], help="genera nomes un idioma")
    parser.add_argument("--force", action="store_true", help="refes les mostres existents")
    args = parser.parse_args()

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("Falta edge-tts. Instal·la'l amb:  pip install edge-tts")
        return 1

    SAMPLES.mkdir(exist_ok=True)
    selected = [s for s in SAMPLES_SPEC if not args.only or s["lang"] == args.only]

    for spec in selected:
        wav = SAMPLES / f"{spec['name']}.wav"
        ref = SAMPLES / f"{spec['name']}.txt"
        if wav.exists() and not args.force:
            print(f"  = {wav.name} (ja existeix)")
            continue

        mp3 = SAMPLES / f"_{spec['name']}.mp3"
        try:
            asyncio.run(synth(spec, mp3))
            mp3_to_wav(mp3, wav)
            ref.write_text(spec["text"] + "\n", encoding="utf-8")
            print(f"  + {wav.name}  [{spec['lang']}]  {spec['text'][:60]}...")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! ERROR generant {spec['name']}: {exc}")
        finally:
            mp3.unlink(missing_ok=True)

    print(f"\nMostres a: {SAMPLES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
