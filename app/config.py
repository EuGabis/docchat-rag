"""Configuração lida de variáveis de ambiente (com valores padrão para rodar localmente)."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Carrega um .env simples (CHAVE=valor) sem dependências extras."""
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Banco: se DATABASE_URL não vier, sobe um PostgreSQL + pgvector embutido (pgserver) em ./.pgdata
    database_url: str = os.getenv("DATABASE_URL", "")
    embedded_pg_dir: Path = ROOT_DIR / ".pgdata"

    # Embeddings locais (multilíngue, 384 dimensões) — não precisam de chave nem internet após o download
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "384"))
    models_cache: Path = ROOT_DIR / ".models"

    # Geração com Claude (opcional: sem chave o app responde em modo "somente recuperação")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
    claude_effort: str = os.getenv("CLAUDE_EFFORT", "medium")

    # Recuperação
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    top_k: int = int(os.getenv("TOP_K", "6"))
    candidates: int = int(os.getenv("CANDIDATES", "20"))

    @property
    def llm_enabled(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


settings = Settings()
