#!/usr/bin/env python3
"""Grava una mostra de veu per al benchmark.

Us:
  python record.py --name ca_01                  # Enter per comencar i per aturar
  python record.py --name ca_01 --seconds 8      # durada fixa
  python record.py --name ca_01 --text "Hola..." # tambe desa la referencia per al WER

La mostra es desa a samples/<name>.wav (16 kHz mono).
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"


def resample_linear(data, src_rate: int, dst_rate: int):
    import numpy as np

    if src_rate == dst_rate:
        return data
    n_out = int(round(len(data) * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, data).astype(np.int16)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grava una mostra de veu")
    parser.add_argument("--name", default="prova", help="nom del fitxer (sense extensio)")
    parser.add_argument("--seconds", type=float, default=None,
                        help="durada fixa; si no s'indica, Enter per aturar")
    parser.add_argument("--text", default=None, help="text de referencia opcional")
    parser.add_argument("--device", default=None, help="index o nom del microfon")
    args = parser.parse_args()

    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        print("Falten dependencies. Executa:  pip install sounddevice numpy")
        return 1

    SAMPLES.mkdir(exist_ok=True)
    out = SAMPLES / f"{args.name}.wav"

    try:
        info = sd.query_devices(args.device, kind="input")
        device_name = info["name"]
        channels = 1
        rate = int(info["default_samplerate"])
        try:
            sd.check_input_settings(device=args.device, channels=channels,
                                    samplerate=16000, dtype="int16")
            rate = 16000
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        print(f"No s'ha trobat cap microfon: {exc}")
        return 1

    print(f"Microfon : {device_name}")
    print(f"Mostreig : {rate} Hz")

    if args.seconds:
        print(f"Gravant {args.seconds:.0f}s...")
        audio = sd.rec(int(args.seconds * rate), samplerate=rate, channels=channels,
                       dtype="int16", device=args.device)
        sd.wait()
        data = audio.reshape(-1)
    else:
        input("Prem Enter per comencar a gravar...")
        chunks = []

        def callback(indata, frames, time_info, status):  # noqa: ANN001
            if status:
                print(status, file=sys.stderr)
            chunks.append(indata.copy())

        print("Gravant... prem Enter per aturar.")
        with sd.InputStream(samplerate=rate, channels=channels, dtype="int16",
                            device=args.device, callback=callback):
            input()
        data = np.concatenate(chunks).reshape(-1) if chunks else np.zeros(0, dtype=np.int16)

    if len(data) == 0:
        print("No s'ha gravat res.")
        return 1

    peak = int(np.abs(data).max())
    rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
    data = resample_linear(data, rate, 16000)

    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(data.astype(np.int16).tobytes())

    duration = len(data) / 16000
    print(f"Desat: {out}  ({duration:.1f}s, pic {peak}, rms {rms:.0f})")
    if rms < 100:
        print("Avís: el senyal es molt baix. Comprova el microfon o apuja el guany.")

    if args.text:
        out.with_suffix(".txt").write_text(args.text.strip() + "\n", encoding="utf-8")
        print(f"Referencia: {out.with_suffix('.txt').name}")
    else:
        print("Consell: grava tambe la referencia per mesurar el WER, p. ex.")
        print(f'  python record.py --name {args.name} --text "el que has dit"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
