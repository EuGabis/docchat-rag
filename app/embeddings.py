"""Embeddings locais com fastembed (ONNX). O modelo é carregado uma vez e reaproveitado."""

from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

from .config import settings

_lock = threading.Lock()


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    settings.models_cache.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(settings.embedding_model, cache_dir=str(settings.models_cache))


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    if not texts:
        return []
    with _lock:  # o runtime ONNX já paraleliza internamente
        vectors = list(_model().embed(texts, batch_size=32))
    return [np.asarray(v, dtype=np.float32) for v in vectors]


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]
