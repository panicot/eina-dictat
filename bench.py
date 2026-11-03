#!/usr/bin/env python3
"""Benchmark de transcripcio local amb faster-whisper.

Mesura, per a cada model i cada mostra d'audio:
  - temps de carrega (inclosa la primera descarrega)
  - latencia per transcripcio
  - RTF (latencia / durada de l'audio; < 1.0 vol dir mes rapid que el temps real)
  - WER si hi ha un .txt amb la referencia al costat de l'audio

Us:
  python bench.py                          # base i small, idioma ca
  python bench.py --models base small medium
  python bench.py --language auto
  python bench.py --runs 3 --beam 5
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
RESULTS = ROOT / "results"
MODELS = ROOT / "models"

MEDIA_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm"}


def patch_pyav() -> None:
    """faster-whisper 1.2.1 passa `metadata_errors` a av.open, eliminat a PyAV 15+.

    Ho embolcallem perque el benchmark funcioni amb la versio instal·lada.
    """
    import av

    major = int(av.__version__.split(".")[0])
    if major < 15 or getattr(av.open, "_cw_patched", False):
        return
    original = av.open

    def open_compat(*args, metadata_errors=None, **kwargs):  # noqa: ANN001
        return original(*args, **kwargs)

    open_compat._cw_patched = True  # type: ignore[attr-defined]
    av.open = open_compat  # type: ignore[assignment]
    print(f"  (pegat de compatibilitat PyAV {av.__version__})")


def find_samples(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in MEDIA_EXT)


def media_duration(path: Path) -> float:
    import av

    with av.open(str(path)) as container:
        if container.duration is not None:
            return container.duration / av.time_base
    return 0.0


def normalize(text: str) -> list[str]:
    cleaned = "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in text)
    return cleaned.split()


def wer(reference: str, hypothesis: str) -> float:
    ref = normalize(reference)
    hyp = normalize(hypothesis)
    if not ref:
        return 0.0
    # Levenshtein sobre paraules
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i]
        for j, h in enumerate(hyp, start=1):
            cost = 0 if r == h else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1] / len(ref)


def read_reference(audio: Path) -> str | None:
    ref = audio.with_suffix(".txt")
    if ref.exists():
        return ref.read_text(encoding="utf-8").strip()
    return None


def human(x: float) -> str:
    return f"{x:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark faster-whisper en CPU")
    parser.add_argument("--models", nargs="+", default=["base", "small"],
                        help="models de faster-whisper (default: base small)")
    parser.add_argument("--language", default="ca",
                        help="ca, es, en o 'auto' (default: ca)")
    parser.add_argument("--runs", type=int, default=2,
                        help="transcripcions mesurades per mostra (default: 2)")
    parser.add_argument("--beam", type=int, default=1,
                        help="beam size; 1 es el mes rapid (default: 1)")
    parser.add_argument("--threads", type=int, default=4,
                        help="fils de CPU (default: 4)")
    parser.add_argument("--compute", default="int8",
                        help="int8, int8_float32, float32 (default: int8)")
    parser.add_argument("--no-vad", action="store_true", help="desactiva el VAD")
    parser.add_argument("--samples-dir", type=Path, default=SAMPLES)
    parser.add_argument("--only", default=None,
                        help="filtra mostres pel prefix del nom, p. ex. 'ca' o 'ca_01'")
    args = parser.parse_args()

    samples_dir = args.samples_dir
    samples = find_samples(samples_dir)
    if args.only:
        samples = [s for s in samples if s.stem.startswith(args.only)]
    if not samples:
        print(f"No hi ha mostres a {samples_dir}.")
        print("Genera'n amb:  python make_samples.py")
        print("O grava les teves:  python record.py --name ca_01")
        return 1

    print("=" * 78)
    print("BENCHMARK faster-whisper")
    print("=" * 78)
    print(f"Python      : {platform.python_version()} ({platform.machine()})")
    print(f"CPU         : {platform.processor() or 'desconeguda'}")
    print(f"Fils        : {args.threads}")
    print(f"Idioma      : {args.language}")
    print(f"Beam        : {args.beam}   Compute: {args.compute}   VAD: {not args.no_vad}")
    print(f"Mostres     : {len(samples)}")
    for s in samples:
        ref = " + referencia" if read_reference(s) else ""
        print(f"  - {s.name}  ({media_duration(s):.1f}s){ref}")
    print()

    patch_pyav()
    from faster_whisper import WhisperModel

    RESULTS.mkdir(exist_ok=True)
    all_results: dict = {}
    started = datetime.now()

    for model_name in args.models:
        print("-" * 78)
        print(f"MODEL: {model_name}")
        print("-" * 78)

        load_start = time.perf_counter()
        try:
            model = WhisperModel(
                model_name,
                device="cpu",
                compute_type=args.compute,
                cpu_threads=args.threads,
                download_root=str(MODELS),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR carregant {model_name}: {exc}")
            continue
        load_s = time.perf_counter() - load_start
        print(f"  carrega: {load_s:.2f}s")

        # Escalfament: la primera inferencia reserva memoria i es mes lenta.
        warm = samples[0]
        try:
            segs, _ = model.transcribe(
                str(warm), language=None if args.language == "auto" else args.language,
                beam_size=args.beam, vad_filter=not args.no_vad,
                condition_on_previous_text=False, without_timestamps=True,
            )
            "".join(s.text for s in segs)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR en escalfament: {exc}")
            del model
            continue

        entry = {"load_s": round(load_s, 3), "files": {}}
        for sample in samples:
            duration = media_duration(sample)
            latencies: list[float] = []
            text = ""
            detected = ""
            for _ in range(max(1, args.runs)):
                t0 = time.perf_counter()
                segments, info = model.transcribe(
                    str(sample),
                    language=None if args.language == "auto" else args.language,
                    beam_size=args.beam,
                    vad_filter=not args.no_vad,
                    condition_on_previous_text=False,
                    without_timestamps=True,
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                latencies.append(time.perf_counter() - t0)
                detected = f"{info.language} ({info.language_probability:.2f})"

            mean_lat = statistics.mean(latencies)
            rtf = mean_lat / duration if duration else 0.0
            ref = read_reference(sample)
            sample_wer = wer(ref, text) if ref else None

            entry["files"][sample.name] = {
                "audio_s": round(duration, 2),
                "latencies_s": [round(x, 3) for x in latencies],
                "latency_mean_s": round(mean_lat, 3),
                "rtf": round(rtf, 3),
                "language": detected,
                "wer": None if sample_wer is None else round(sample_wer, 3),
                "text": text,
            }

            wer_txt = "-" if sample_wer is None else f"{sample_wer * 100:.1f}%"
            print(f"  {sample.name:<22} audio {duration:5.1f}s  lat {mean_lat:5.2f}s  "
                  f"RTF {rtf:4.2f}  WER {wer_txt:>6}  {detected}")
            print(f"    > {text[:110]}")

        files = entry["files"].values()
        n = len(entry["files"])
        avg_lat = sum(f["latency_mean_s"] for f in files) / n if n else 0
        avg_rtf = sum(f["rtf"] for f in files) / n if n else 0
        wers = [f["wer"] for f in files if f["wer"] is not None]
        avg_wer = sum(wers) / len(wers) if wers else None

        entry["summary"] = {
            "avg_latency_s": round(avg_lat, 3),
            "avg_rtf": round(avg_rtf, 3),
            "avg_wer": None if avg_wer is None else round(avg_wer, 3),
        }
        all_results[model_name] = entry
        print(f"  MITJANA: latencia {avg_lat:.2f}s  RTF {avg_rtf:.2f}"
              + (f"  WER {avg_wer * 100:.1f}%" if avg_wer is not None else ""))
        print()

        del model
        gc.collect()

    if not all_results:
        print("Cap model s'ha pogut executar.")
        return 1

    # ---- Informe ----
    print("=" * 78)
    print("RESUM")
    print("=" * 78)
    name_w = max(12, max(len(n) for n in all_results) + 2)
    print(f"{'model':<{name_w}}{'carrega':>9}{'latencia':>10}{'RTF':>7}{'WER':>8}{'velocitat':>11}")
    for name, e in all_results.items():
        s = e["summary"]
        w = "-" if s["avg_wer"] is None else f"{s['avg_wer'] * 100:.1f}%"
        print(f"{name:<{name_w}}{e['load_s']:>8.2f}s{s['avg_latency_s']:>9.2f}s"
              f"{s['avg_rtf']:>7.2f}{w:>8}{1 / max(s['avg_rtf'], 1e-9):>10.1f}x")

    stamp = started.strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS / f"bench_{stamp}.json"
    json_path.write_text(json.dumps({
        "timestamp": started.isoformat(),
        "language": args.language,
        "beam": args.beam,
        "compute": args.compute,
        "vad": not args.no_vad,
        "results": all_results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# Benchmark {started:%Y-%m-%d %H:%M}", "",
          f"- Idioma: `{args.language}`  Beam: `{args.beam}`  Compute: `{args.compute}`  VAD: `{not args.no_vad}`",
          "", "| Model | Carrega (s) | Latencia mitjana (s) | RTF | WER |", "|---|---|---|---|---|"]
    for name, e in all_results.items():
        s = e["summary"]
        wer_cell = "-" if s["avg_wer"] is None else f"{s['avg_wer'] * 100:.1f}%"
        md.append(f"| {name} | {e['load_s']:.2f} | {s['avg_latency_s']:.2f} | "
                  f"{s['avg_rtf']:.2f} | {wer_cell} |")
    md += ["", "## Detall", ""]
    for name, e in all_results.items():
        md.append(f"### {name}")
        md.append("")
        for fname, f in e["files"].items():
            file_wer = "-" if f["wer"] is None else f"{f['wer'] * 100:.1f}%"
            md.append(f"- **{fname}** — audio {f['audio_s']}s, latencia {f['latency_mean_s']}s, "
                      f"RTF {f['rtf']}, idioma {f['language']}, WER {file_wer}")
            md.append(f"  > {f['text']}")
        md.append("")
    md_path = RESULTS / f"bench_{stamp}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print()
    print(f"Resultats desats a: {json_path}")
    print(f"Informe llegible  : {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
