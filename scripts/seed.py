"""Indexa os documentos de exemplo de data/samples (pode rodar várias vezes: substitui as versões)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db  # noqa: E402
from app.ingest import ingest_file  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def main() -> None:
    init_db()
    started = time.perf_counter()
    for path in sorted(SAMPLES.glob("*.md")):
        result = ingest_file(path.name, path.read_bytes())
        print(f"✓ {result.title:<55} {result.chunks:>3} trechos")
    print(f"Pronto em {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
