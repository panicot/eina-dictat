"""Descàrrega d'un model en un procés aïllat.

`huggingface_hub` no permet interrompre una descàrrega a mig camí: els seus
fils interns segueixen baixant encara que un `tqdm` falli. Per poder cancel·lar
de veritat, la descàrrega es fa en un procés fill que es pot matar. Els fitxers
parcials es conserven, així una descàrrega posterior reprèn on era.
"""

from __future__ import annotations

import sys

from huggingface_hub import snapshot_download

from app.engine import MODELS_DIR


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("ús: python -m app.download_job REPO_ID", file=sys.stderr)
        return 2
    try:
        snapshot_download(
            repo_id=argv[0],
            cache_dir=str(MODELS_DIR),
            max_workers=1,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
