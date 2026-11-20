"""Busca híbrida: similaridade vetorial (pgvector) + full-text (tsvector), fundidas com RRF.

Por que híbrida? Embeddings entendem o sentido ("quanto custa" ~ "valor da mensalidade"),
enquanto a busca textual acerta termos exatos (siglas, códigos, nomes próprios). A Reciprocal
Rank Fusion combina as duas listas só pela posição de cada item, sem precisar calibrar escalas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .config import settings
from .db import connect
from .embeddings import embed_query

Mode = Literal["hybrid", "vector", "keyword"]
RRF_K = 60  # constante padrão da literatura (Cormack et al., 2009)


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    document_title: str
    source: str
    heading: str
    content: str
    score: float = 0.0
    vector_rank: int | None = None
    keyword_rank: int | None = None
    similarity: float | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "source": self.source,
            "heading": self.heading,
            "content": self.content,
            "score": round(self.score, 5),
            "vector_rank": self.vector_rank,
            "keyword_rank": self.keyword_rank,
            "similarity": None if self.similarity is None else round(self.similarity, 4),
        }


def rrf_fuse(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion: score(d) = Σ 1 / (k + posição_d) em cada lista (posição começa em 1)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position)
    return scores


_SELECT = """
    SELECT c.id, c.document_id, d.title, d.source, c.heading, c.content
    FROM chunks c JOIN documents d ON d.id = c.document_id
"""


def _vector_search(conn, query: str, limit: int) -> list[tuple[int, float]]:
    qvec = embed_query(query)
    rows = conn.execute(
        """
        SELECT id, 1 - (embedding <=> %(q)s) AS similarity
        FROM chunks
        ORDER BY embedding <=> %(q)s
        LIMIT %(limit)s
        """,
        {"q": qvec, "limit": limit},
    ).fetchall()
    return [(row[0], float(row[1])) for row in rows]


def _keyword_search(conn, query: str, limit: int) -> list[int]:
    # plainto_tsquery junta os termos com AND; trocamos por OR para perguntas em linguagem natural
    rows = conn.execute(
        """
        WITH q AS (
            SELECT NULLIF(replace(plainto_tsquery('portuguese', %(text)s)::text, '&', '|'), '')::tsquery AS query
        )
        SELECT c.id
        FROM chunks c, q
        WHERE q.query IS NOT NULL AND c.tsv @@ q.query
        ORDER BY ts_rank_cd(c.tsv, q.query, 32) DESC
        LIMIT %(limit)s
        """,
        {"text": query, "limit": limit},
    ).fetchall()
    return [row[0] for row in rows]


def search(query: str, top_k: int | None = None, mode: Mode = "hybrid") -> list[Hit]:
    top_k = top_k or settings.top_k
    limit = max(settings.candidates, top_k)
    with connect() as conn:
        vector = _vector_search(conn, query, limit) if mode in ("hybrid", "vector") else []
        keyword = _keyword_search(conn, query, limit) if mode in ("hybrid", "keyword") else []

        vector_ids = [cid for cid, _ in vector]
        similarity = dict(vector)
        scores = rrf_fuse([lst for lst in (vector_ids, keyword) if lst])
        ranked = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
        if not ranked:
            return []

        rows = conn.execute(_SELECT + " WHERE c.id = ANY(%(ids)s)", {"ids": ranked}).fetchall()

    by_id = {row[0]: row for row in rows}
    vrank = {cid: i for i, cid in enumerate(vector_ids, start=1)}
    krank = {cid: i for i, cid in enumerate(keyword, start=1)}
    hits = []
    for cid in ranked:
        row = by_id[cid]
        hits.append(
            Hit(
                chunk_id=row[0],
                document_id=row[1],
                document_title=row[2],
                source=row[3],
                heading=row[4],
                content=row[5],
                score=scores[cid],
                vector_rank=vrank.get(cid),
                keyword_rank=krank.get(cid),
                similarity=similarity.get(cid),
            )
        )
    return hits
