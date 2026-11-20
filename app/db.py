"""Conexão com PostgreSQL + pgvector e criação do schema."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector

from .config import settings

_lock = threading.Lock()
_embedded_server = None
_resolved_url: str | None = None

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    source      TEXT NOT NULL UNIQUE,
    mime        TEXT NOT NULL,
    chunk_count INT  NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id INT  NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord         INT  NOT NULL,
    heading     TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    embedding   vector({settings.embedding_dim}) NOT NULL,
    -- coluna gerada para busca textual em português (stemming + stopwords)
    tsv         tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('portuguese', heading), 'A') ||
                    setweight(to_tsvector('portuguese', content), 'B')
                ) STORED
);

-- índice aproximado (HNSW) para similaridade de cosseno
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
-- índice invertido para full-text search
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id);
"""


def database_url() -> str:
    """URL do banco: a de DATABASE_URL ou a de um PostgreSQL embutido (pgserver)."""
    global _embedded_server, _resolved_url
    if _resolved_url:
        return _resolved_url
    with _lock:
        if _resolved_url:
            return _resolved_url
        if settings.database_url:
            _resolved_url = settings.database_url
        else:
            import pgserver  # import tardio: só é necessário no modo embutido

            settings.embedded_pg_dir.mkdir(parents=True, exist_ok=True)
            _embedded_server = pgserver.get_server(str(settings.embedded_pg_dir), cleanup_mode="stop")
            _resolved_url = _embedded_server.get_uri()
    return _resolved_url


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url(), autocommit=False) as conn:
        register_vector(conn)
        yield conn


def init_db() -> None:
    # a extensão precisa existir antes de registrar o tipo vector na conexão
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    with connect() as conn:
        conn.execute(SCHEMA)
        conn.commit()
