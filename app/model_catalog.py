"""Cataleg de models locals i utilitats per saber quins hi ha instal·lats.

Els identificadors són repositoris de Hugging Face. faster-whisper també
accepta àlies curts (`base`, `small`...), que resolem aquí perquè la interfície
pugui treballar sempre amb un identificador estable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.engine import MODELS_DIR

LANGUAGE_LABELS = {"ca": "Català", "es": "Castellà", "en": "Anglès"}

ALIASES = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
}


@dataclass(frozen=True)
class ModelInfo:
    repo_id: str
    name: str
    size_mb: int
    languages: tuple[str, ...]
    tags: tuple[str, ...]
    description: str
    speed: str
    quality: str
    license: str = "MIT"
    recommended: bool = False

    @property
    def is_multilingual(self) -> bool:
        return len(self.languages) > 1

    @property
    def language_label(self) -> str:
        if self.is_multilingual:
            return "Multilingüe"
        return LANGUAGE_LABELS.get(self.languages[0], self.languages[0].upper())


CATALOG: tuple[ModelInfo, ...] = (
    ModelInfo(
        repo_id="Jarbas/faster-whisper-base-ca-cv13",
        name="Jarbas base-ca-cv13",
        size_mb=145,
        languages=("ca",),
        tags=("recomanat", "catala"),
        description="Ajustat en català. El millor equilibri entre qualitat i velocitat en CPU.",
        speed="RTF 0,23",
        quality="WER 9,6 %",
        recommended=True,
    ),
    ModelInfo(
        repo_id="Systran/faster-whisper-base",
        name="Whisper base",
        size_mb=145,
        languages=("ca", "es", "en"),
        tags=("recomanat", "multilingue"),
        description="El model multilingüe equilibrat per a castellà i anglès.",
        speed="RTF 0,34",
        quality="WER 11,1 % ES",
        recommended=True,
    ),
    ModelInfo(
        repo_id="Jarbas/faster-whisper-small-ca-cv13",
        name="Jarbas small-ca-cv13",
        size_mb=480,
        languages=("ca",),
        tags=("millor-qualitat", "catala"),
        description="Més precís en català, però unes tres vegades més lent en aquest equip.",
        speed="RTF 0,64",
        quality="WER 11,1 %",
    ),
    ModelInfo(
        repo_id="Systran/faster-whisper-small",
        name="Whisper small",
        size_mb=480,
        languages=("ca", "es", "en"),
        tags=("millor-qualitat", "multilingue"),
        description="Més qualitat en llengües no catalanes. Recomanat només si tens pressa zero.",
        speed="RTF 0,82",
        quality="WER 11,0 % CA",
    ),
    ModelInfo(
        repo_id="Systran/faster-whisper-tiny",
        name="Whisper tiny",
        size_mb=75,
        languages=("ca", "es", "en"),
        tags=("rapid", "multilingue"),
        description="Molt ràpid i molt lleuger. Útil per proves o equips molt justos.",
        speed="RTF 0,08",
        quality="Precisió baixa",
    ),
    ModelInfo(
        repo_id="Systran/faster-whisper-medium",
        name="Whisper medium",
        size_mb=1530,
        languages=("ca", "es", "en"),
        tags=("millor-qualitat", "multilingue"),
        description="Bona qualitat, però massa lent per dictar en un N100 sense GPU.",
        speed="RTF ~1,8",
        quality="Alta",
    ),
    ModelInfo(
        repo_id="projecte-aina/faster-whisper-large-v3-ca-3catparla",
        name="Aina large-v3 3CatParla",
        size_mb=3087,
        languages=("ca",),
        tags=("millor-qualitat", "catala"),
        description=(
            "Whisper large-v3 afinat amb 3CatParla pel BSC. Molt més precís en "
            "català, però pensat per GPU: en un N100 pot trigar desenes de "
            "segons per frase. No afegeix puntuació."
        ),
        speed="Molt lent en CPU",
        quality="Màxima en català",
        license="Apache-2.0",
    ),
    ModelInfo(
        repo_id="Systran/faster-whisper-large-v3",
        name="Whisper large-v3",
        size_mb=3090,
        languages=("ca", "es", "en"),
        tags=("millor-qualitat", "multilingue"),
        description="La màxima qualitat de Whisper. Només té sentit amb GPU.",
        speed="Molt lent en CPU",
        quality="Màxima",
    ),
)

BY_REPO = {info.repo_id: info for info in CATALOG}


def resolve(value: str | None) -> str:
    """Converteix un àlies (`base`) o un ID en un ID de repositori."""
    if not value:
        return ALIASES["base"]
    return ALIASES.get(value, value)


def info_for(value: str | None) -> ModelInfo | None:
    return BY_REPO.get(resolve(value))


def display_name(value: str | None) -> str:
    info = info_for(value)
    return info.name if info else (value or "Cap model")


def repo_dir(repo_id: str) -> Path:
    return MODELS_DIR / ("models--" + resolve(repo_id).replace("/", "--"))


def is_installed(repo_id: str) -> bool:
    base = repo_dir(repo_id)
    snapshots = base / "snapshots"
    if not snapshots.is_dir():
        return False
    for snapshot in snapshots.iterdir():
        if (snapshot / "model.bin").is_file():
            return True
    # Alguns models petits porten els fitxers directament a l'arrel.
    return (base / "model.bin").is_file()


def installed_size_mb(repo_id: str) -> int:
    base = repo_dir(repo_id)
    total = 0
    for folder in (base / "blobs", base / "snapshots"):
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                pass
        if total:
            break
    return max(1, round(total / (1024 * 1024))) if total else 0


def models_for_language(language: str, installed_only: bool = True) -> list[ModelInfo]:
    result = []
    for info in CATALOG:
        if language not in info.languages and "multilingue" not in info.tags:
            continue
        if installed_only and not is_installed(info.repo_id):
            continue
        result.append(info)
    result.sort(key=lambda item: (not item.recommended, item.size_mb))
    return result


def installed_models() -> list[ModelInfo]:
    return [info for info in CATALOG if is_installed(info.repo_id)]


def installed_total_mb() -> int:
    return sum(installed_size_mb(info.repo_id) for info in installed_models())


def recommended_for(language: str) -> ModelInfo | None:
    for info in CATALOG:
        if info.recommended and (language in info.languages or info.is_multilingual):
            return info
    return None
