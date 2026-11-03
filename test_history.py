"""Prova les transcripcions reals del historial contra els modes de veu."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
from app.config import load  # noqa: E402
from app.textmodes import TextModes  # noqa: E402

cfg = load()
modes = TextModes(cfg)

print("=== Simulació de dictada (historial real) ===")
for line in (ROOT / "history.jsonl").read_text(encoding="utf-8").splitlines():
    record = json.loads(line)
    raw = record["text"]
    out = modes.transform(raw)
    print(f"\nRAW : {raw}")
    print(f"OUT : {out}")
    if modes.events:
        print(f"     events: {modes.events}")
