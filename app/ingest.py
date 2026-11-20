"""Pipeline de ingestão: arquivo -> seções -> trechos -> embeddings -> PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass

from .chunking import chunk_sections
from .config import settings
from .db import connect
from .embeddings import embed_texts
from .loaders import load_sections, title_from


@dataclass
class IngestResult:
    document_id: int
    title: str
    source: str
    chunks: int
    replaced: bool


def ingest_file(filename: str, data: bytes, source: str | None = None) -> IngestResult:
    source = source or filename
    mime, sections = load_sections(filename, data)
    title = title_from(filename, sections)
    chunks = chunk_sections(sections, settings.chunk_size, settings.chunk_overlap)

    # o título da seção entra no texto embutido: ajuda a busca a entender o contexto do trecho
    vectors = embed_texts([f"{c.heading}\n{c.content}" if c.heading else c.content for c in chunks])

    with connect() as conn:
        existing = conn.execute("SELECT id FROM documents WHERE source = %s", (source,)).fetchone()
        if existing:  # reenvio do mesmo arquivo substitui a versão anterior
            conn.execute("DELETE FROM documents WHERE id = %s", (existing[0],))
        doc_id = conn.execute(
            "INSERT INTO documents (title, source, mime, chunk_count) VALUES (%s, %s, %s, %s) RETURNING id",
            (title, source, mime, len(chunks)),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (document_id, ord, heading, content, embedding) VALUES (%s, %s, %s, %s, %s)",
                [(doc_id, c.ord, c.heading, c.content, v) for c, v in zip(chunks, vectors)],
            )
        conn.commit()
    return IngestResult(doc_id, title, source, len(chunks), bool(existing))


def list_documents() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, source, mime, chunk_count, created_at FROM documents ORDER BY title"
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "source": r[2], "mime": r[3], "chunks": r[4], "created_at": r[5].isoformat()}
        for r in rows
    ]


def delete_document(document_id: int) -> bool:
    with connect() as conn:
        deleted = conn.execute("DELETE FROM documents WHERE id = %s RETURNING id", (document_id,)).fetchone()
        conn.commit()
    return bool(deleted)


def stats() -> dict:
    with connect() as conn:
        docs, chunks = conn.execute(
            "SELECT (SELECT count(*) FROM documents), (SELECT count(*) FROM chunks)"
        ).fetchone()
    return {"documents": docs, "chunks": chunks}
