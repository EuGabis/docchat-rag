"""Divisão de documentos em trechos (chunks) que respeitam a estrutura do texto.

Estratégia:
1. Separa por seções (títulos Markdown ou páginas de PDF), guardando o título como contexto.
2. Dentro de cada seção, junta parágrafos até ~chunk_size caracteres.
3. Repete o fim do trecho anterior (overlap) para não perder contexto na fronteira.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Section:
    heading: str
    text: str


@dataclass(frozen=True)
class Chunk:
    ord: int
    heading: str
    content: str


def split_markdown_sections(markdown: str) -> list[Section]:
    """Quebra Markdown por títulos, mantendo o caminho hierárquico (ex.: 'Cursos > Piloto Privado')."""
    sections: list[Section] = []
    path: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(Section(" > ".join(path), text))
        buffer.clear()

    for line in markdown.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            path[:] = path[: level - 1] + [match.group(2).strip()]
        else:
            buffer.append(line)
    flush()
    return sections


def _paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # remove marcadores de citação do Markdown ("> ") e espaços repetidos
    paras = [re.sub(r"^>\s?", "", p, flags=re.MULTILINE) for p in paras]
    return [re.sub(r"[ \t]+", " ", p) for p in paras]


def _split_long(paragraph: str, size: int) -> list[str]:
    """Parágrafos maiores que o limite são cortados em frases."""
    if len(paragraph) <= size:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
    parts, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > size:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    # frases gigantes (sem pontuação) ainda são cortadas por tamanho
    out: list[str] = []
    for part in parts:
        out.extend(part[i : i + size] for i in range(0, len(part), size))
    return out


def _tail(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return text if overlap > 0 else ""
    cut = text[-overlap:]
    space = cut.find(" ")
    return cut[space + 1 :] if 0 <= space < len(cut) - 1 else cut


def chunk_sections(sections: list[Section], size: int = 900, overlap: int = 150) -> list[Chunk]:
    if overlap >= size:
        raise ValueError("overlap precisa ser menor que size")
    chunks: list[Chunk] = []
    for section in sections:
        pieces: list[str] = []
        for para in _paragraphs(section.text):
            pieces.extend(_split_long(para, size))

        current = ""
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if current and len(candidate) > size:
                chunks.append(Chunk(len(chunks), section.heading, current))
                tail = _tail(current, overlap)
                current = f"{tail}\n\n{piece}" if tail else piece
            else:
                current = candidate
        if current.strip():
            chunks.append(Chunk(len(chunks), section.heading, current))
    return chunks
