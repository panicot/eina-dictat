"""Motor de transcripcio basat en faster-whisper, amb un model per idioma."""

from __future__ import annotations

import re
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"


def _patch_pyav() -> None:
    """faster-whisper 1.2.1 passa `metadata_errors` a av.open (eliminat a PyAV 15+)."""
    try:
        import av
    except ImportError:
        return
    major = int(av.__version__.split(".")[0])
    if major < 15 or getattr(av.open, "_cw_patched", False):
        return
    original = av.open

    def open_compat(*args, metadata_errors=None, **kwargs):  # noqa: ANN001
        return original(*args, **kwargs)

    open_compat._cw_patched = True  # type: ignore[attr-defined]
    av.open = open_compat  # type: ignore[assignment]


class Engine:
    def __init__(self, config) -> None:  # noqa: ANN001
        self.cfg = config
        self._models: dict[str, object] = {}
        self._lock = threading.Lock()
        self.on_status = lambda message: None  # noqa: E731
        self._build_dictionary()

    def _build_dictionary(self) -> None:
        self._dictionary: list[tuple[re.Pattern[str], str]] = [
            (re.compile(rf"\b{re.escape(src)}\b", re.IGNORECASE), dst)
            for src, dst in self.cfg.dictionary.items()
        ]

    def reload_config(self, config) -> None:  # noqa: ANN001
        """Aplica una configuracio nova i buida els models carregats."""
        self.cfg = config
        self._build_dictionary()
        with self._lock:
            self._models.clear()

    def _load(self, language: str):
        name = self.cfg.model_for(language)
        model = self._models.get(name)
        if model is None:
            _patch_pyav()
            from faster_whisper import WhisperModel

            self.on_status(f"Carregant model {name}...")
            model = WhisperModel(
                name,
                device="cpu",
                compute_type=self.cfg.compute_type,
                cpu_threads=self.cfg.threads,
                download_root=str(MODELS_DIR),
            )
            self._models[name] = model
            self.on_status(f"Model a punt: {name}")
        return model

    def preload(self, language: str) -> None:
        with self._lock:
            self._load(language)

    def _run(self, source, language: str) -> tuple[str, float]:
        model = self._load(language)
        segments, info = model.transcribe(
            source,
            language=language,
            beam_size=self.cfg.beam_size,
            vad_filter=self.cfg.vad,
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=self.cfg.prompt_for(language),
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, float(info.language_probability)

    def transcribe(self, audio: np.ndarray, language: str) -> tuple[str, float]:
        if audio.size < int(0.25 * 16000):
            return "", 0.0
        with self._lock:
            text, probability = self._run(audio, language)
        return self.postprocess(text), probability

    def transcribe_file(self, path: str | Path, language: str) -> tuple[str, float]:
        with self._lock:
            text, probability = self._run(str(path), language)
        return self.postprocess(text), probability

    def postprocess(self, text: str) -> str:
        text = " ".join(text.split())
        for pattern, replacement in self._dictionary:
            text = pattern.sub(replacement, text)
        return text.strip()
