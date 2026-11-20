import pytest

from app.chunking import Section, chunk_sections, split_markdown_sections

MD = """# Manual

Introdução curta.

## Cursos

Primeiro parágrafo do curso.

Segundo parágrafo do curso.

### Piloto

Texto do piloto.
"""


def test_markdown_sections_keep_heading_path():
    sections = split_markdown_sections(MD)
    assert [s.heading for s in sections] == ["Manual", "Manual > Cursos", "Manual > Cursos > Piloto"]
    assert sections[1].text.startswith("Primeiro parágrafo")


def test_small_sections_become_single_chunks():
    chunks = chunk_sections(split_markdown_sections(MD), size=500, overlap=50)
    assert len(chunks) == 3
    assert [c.ord for c in chunks] == [0, 1, 2]
    assert "Segundo parágrafo" in chunks[1].content


def test_long_section_is_split_with_overlap():
    paragraphs = [f"Parágrafo {i} " + "palavra " * 20 for i in range(10)]
    chunks = chunk_sections([Section("Longa", "\n\n".join(paragraphs))], size=300, overlap=60)
    assert len(chunks) > 1
    assert all(len(c.content) <= 300 + 60 + 2 for c in chunks)
    # o começo de cada trecho repete o final do anterior
    for prev, nxt in zip(chunks, chunks[1:]):
        assert prev.content[-20:].split()[-1] in nxt.content[:120]


def test_giant_paragraph_without_punctuation_is_cut():
    chunks = chunk_sections([Section("", "x" * 2000)], size=500, overlap=0)
    assert len(chunks) == 4


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_sections([Section("", "texto")], size=100, overlap=100)
