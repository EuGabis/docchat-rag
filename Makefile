PYTHON ?= python3
PY ?= .venv/bin/python

.PHONY: install seed run test eval db

install:       ## cria o ambiente virtual (ex.: make install PYTHON=python3.12)
	$(PYTHON) -m venv .venv && .venv/bin/pip install -r requirements.txt

db:            ## sobe o PostgreSQL + pgvector no Docker (opcional)
	docker compose up -d

seed:          ## indexa os documentos de exemplo
	$(PY) scripts/seed.py

run:           ## sobe a API + interface em http://localhost:8000
	$(PY) -m uvicorn app.main:app --reload --port 8000

test:
	$(PY) -m pytest -q

eval:          ## compara busca vetorial x palavra-chave x híbrida
	$(PY) scripts/eval_retrieval.py
