"""Leitura de arquivos (Markdown, texto e PDF) para seções de texto."""

from __future__ import annotations

import io
from pathlib import PurePath

from pypdf import PdfReader

from .chunking import Section, split_markdown_sections

SUPPORTED = {".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}


class UnsupportedFileError(ValueError):
    pass


def detect_mime(filename: str) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise UnsupportedFileError(f"Formato não suportado: {ext or 'sem extensão'}. Use .md, .txt ou .pdf")
    return SUPPORTED[ext]


def title_from(filename: str, sections: list[Section]) -> str:
    """Usa o primeiro título do documento; se não houver, o nome do arquivo."""
    for section in sections:
        if section.heading:
            return section.heading.split(" > ")[0]
    return PurePath(filename).stem.replace("-", " ").replace("_", " ").strip().capitalize()


def load_sections(filename: str, data: bytes) -> tuple[str, list[Section]]:
    mime = detect_mime(filename)
    if mime == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        sections = [
            Section(f"Página {number}", (page.extract_text() or "").strip())
            for number, page in enumerate(reader.pages, start=1)
        ]
        sections = [s for s in sections if s.text]
    else:
        text = data.decode("utf-8", errors="replace")
        sections = split_markdown_sections(text) if mime == "text/markdown" else [Section("", text)]
    if not sections:
        raise UnsupportedFileError("Não encontrei texto neste arquivo (PDF escaneado precisa de OCR).")
    return mime, sections
