"""API HTTP (FastAPI) + interface web do DocChat RAG."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Iterator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT_DIR, settings
from .db import init_db
from .embeddings import embed_query
from .generation import answer
from .ingest import delete_document, ingest_file, list_documents, stats
from .loaders import UnsupportedFileError
from .retrieval import Mode, search

STATIC_DIR = ROOT_DIR / "app" / "static"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    embed_query("aquecimento")  # carrega o modelo de embeddings antes da primeira pergunta
    yield


app = FastAPI(title="DocChat RAG", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=settings.top_k, ge=1, le=20)
    mode: Mode = "hybrid"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm": {"enabled": settings.llm_enabled, "model": settings.claude_model if settings.llm_enabled else None},
        "embedding_model": settings.embedding_model,
        **stats(),
    }


@app.get("/api/documents")
def documents() -> list[dict]:
    return list_documents()


@app.post("/api/documents", status_code=201)
def upload(file: UploadFile = File(...)) -> dict:
    # rota síncrona: o FastAPI roda em thread, sem travar o event loop durante os embeddings
    data = file.file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Arquivo maior que 15 MB.")
    try:
        result = ingest_file(file.filename or "documento.txt", data)
    except UnsupportedFileError as exc:
        raise HTTPException(415, str(exc)) from exc
    return result.__dict__


@app.delete("/api/documents/{document_id}", status_code=204)
def remove(document_id: int) -> None:
    if not delete_document(document_id):
        raise HTTPException(404, "Documento não encontrado.")


@app.get("/api/search")
def search_endpoint(q: str, top_k: int = settings.top_k, mode: Mode = "hybrid") -> dict:
    started = time.perf_counter()
    hits = search(q, top_k, mode)
    return {"query": q, "mode": mode, "ms": round((time.perf_counter() - started) * 1000), "hits": [h.as_dict() for h in hits]}


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/ask")
def ask(body: AskRequest) -> StreamingResponse:
    """Responde em Server-Sent Events: primeiro as fontes, depois o texto em streaming com citações."""

    def stream() -> Iterator[str]:
        started = time.perf_counter()
        hits = search(body.question, body.top_k, body.mode)
        retrieval_ms = round((time.perf_counter() - started) * 1000)
        yield _sse("sources", {"retrieval_ms": retrieval_ms, "mode": body.mode, "hits": [h.as_dict() for h in hits]})
        for event in answer(body.question, hits):
            yield _sse(event.pop("type"), event)
        yield _sse("done", {"total_ms": round((time.perf_counter() - started) * 1000), "llm": settings.llm_enabled})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
