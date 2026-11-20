# DocChat RAG

**Perguntas e respostas sobre seus próprios documentos, com fontes citadas.**
Python · FastAPI · PostgreSQL + pgvector · busca híbrida (vetorial + full-text) · Claude com citações nativas.

![DocChat respondendo uma pergunta com as fontes consultadas](docs/screenshot.png)

Você envia PDFs, Markdown ou TXT; o DocChat quebra o texto em trechos, gera embeddings localmente e guarda tudo no PostgreSQL. Na pergunta, ele busca os trechos mais relevantes combinando **similaridade semântica** e **busca por palavra-chave em português**, e o Claude responde citando de qual trecho veio cada informação. A interface mostra por que cada trecho foi escolhido (posição em cada busca e score da fusão).

> A base de exemplo é de uma escola de aviação **fictícia** (cursos, matrícula, regulamento e financeiro).

## Destaques técnicos

- **Busca híbrida com Reciprocal Rank Fusion (RRF):** pgvector (HNSW, cosseno) + `tsvector` com dicionário `portuguese`, fundidos pela posição de cada item. Sem pesos mágicos para calibrar.
- **Citações nativas do Claude:** os trechos vão como blocos `search_result` com `citations` ativadas; a resposta chega em streaming com eventos `citations_delta`, sem pedir "[1]" no prompt nem fazer parsing frágil.
- **Avaliação da recuperação** com perguntas de referência (abaixo): a híbrida acerta mais que cada busca isolada.
- **Embeddings locais** (`paraphrase-multilingual-MiniLM-L12-v2` via fastembed/ONNX): sem custo por documento e sem enviar seus arquivos para uma API de embeddings.
- **Chunking que respeita a estrutura:** quebra por títulos Markdown (guardando o caminho "Seção > Subseção") ou páginas de PDF, junta parágrafos e repete o fim do trecho anterior (overlap).
- **Funciona sem chave:** sem `ANTHROPIC_API_KEY`, entra em modo "somente recuperação" e mostra os trechos encontrados.
- **Robustez:** erros da API tratados por tipo (chave inválida, limite de uso, conexão), `stop_reason` de recusa verificado e *fallback* automático do lado do servidor se o modelo recusar.

## Arquitetura

```mermaid
flowchart LR
    U[Arquivo PDF / MD / TXT] --> L[Loader] --> C[Chunking por seção + overlap]
    C --> E[Embeddings locais<br/>fastembed · 384 dim]
    E --> PG[(PostgreSQL<br/>pgvector HNSW + tsvector GIN)]

    Q[Pergunta] --> V[Busca vetorial]
    Q --> K[Busca full-text<br/>português]
    PG --> V & K
    V --> F[Fusão RRF]
    K --> F
    F --> S[Top-k trechos<br/>como search_result]
    S --> CL[Claude<br/>streaming + citações]
    CL --> UI[Interface web<br/>resposta + fontes]
```

## Avaliação da recuperação

`scripts/eval_retrieval.py` roda 16 perguntas escritas de forma diferente do texto dos documentos (ex.: "Desmarquei o voo em cima da hora, vou pagar?") e verifica se a seção correta volta entre os primeiros resultados.

| Busca           | Hit@3 | MRR   |
|-----------------|:-----:|:-----:|
| Palavra-chave   | 81%   | 0,797 |
| Vetorial        | 94%   | 0,885 |
| **Híbrida (RRF)** | **100%** | **0,938** |

*Hit@3: a seção certa apareceu entre os 3 primeiros trechos. MRR: média de 1/posição do primeiro acerto (1,0 = sempre em primeiro). O índice HNSW é aproximado, então o MRR pode variar levemente quando o índice é reconstruído.*

## Como rodar

Requisitos: Python 3.10 a 3.12 (testado no 3.12; para escolher a versão, use `make install PYTHON=python3.12`). Docker é opcional.

```bash
make install        # cria .venv e instala dependências
cp .env.example .env  # opcional: coloque sua ANTHROPIC_API_KEY
make seed           # indexa os documentos de exemplo
make run            # http://localhost:8000
```

**Banco de dados:** sem `DATABASE_URL`, o app sobe sozinho um PostgreSQL 16 + pgvector embutido em `./.pgdata` (via [pgserver](https://github.com/orm011/pgserver)). Para usar Docker:

```bash
make db   # docker compose up -d (pgvector/pgvector:pg17 na porta 5433)
echo "DATABASE_URL=postgresql://docchat:docchat@localhost:5433/docchat" >> .env
```

Outros comandos: `make test` (testes unitários) e `make eval` (avaliação da busca).

## API

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/documents` | Envia um arquivo (multipart `file`) e indexa. Reenviar o mesmo nome substitui a versão anterior. |
| `GET` | `/api/documents` | Lista documentos indexados |
| `DELETE` | `/api/documents/{id}` | Remove o documento e seus trechos |
| `GET` | `/api/search?q=&mode=hybrid\|vector\|keyword` | Só a recuperação, com ranks e scores |
| `POST` | `/api/ask` | `{"question": "...", "mode": "hybrid"}` → Server-Sent Events: `sources`, `text`, `citation`, `usage`, `done` |
| `GET` | `/api/health` | Status, modelo e contagens |

Documentação interativa em `/docs` (Swagger gerado pelo FastAPI). Links do tipo `/?q=sua+pergunta` já abrem com a resposta.

## Estrutura

```
app/
  chunking.py     divisão em trechos por seção, com overlap
  loaders.py      leitura de PDF, Markdown e TXT
  embeddings.py   embeddings locais (fastembed)
  db.py           schema: pgvector HNSW + tsvector GIN
  retrieval.py    busca vetorial, full-text e fusão RRF
  generation.py   Claude com search_result + citações em streaming
  ingest.py       pipeline de ingestão
  main.py         API FastAPI + SSE
  static/         interface web (HTML/CSS/JS puro)
scripts/          seed e avaliação da recuperação
tests/            testes de chunking, RRF e montagem dos blocos
```

## Próximos passos

- Re-ranking dos candidatos com um modelo cross-encoder
- OCR para PDFs escaneados
- Histórico de conversa (perguntas de acompanhamento)
- Autenticação e uma base de documentos por usuário

## Licença

MIT — veja [LICENSE](LICENSE).

---

Feito por **Gabriel Marcelo** · [LinkedIn](https://www.linkedin.com/in/gabriel-marcelo-dev)
