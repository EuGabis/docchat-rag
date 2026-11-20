"""Geração da resposta com Claude, citando os trechos recuperados.

Os trechos vão para a API como blocos `search_result` com citações ativadas: o próprio Claude
marca de qual trecho veio cada frase (eventos `citations_delta` no streaming), sem precisar
pedir "[1]" no prompt nem fazer parsing frágil do texto.

Sem ANTHROPIC_API_KEY o app continua funcionando em "modo somente recuperação".
"""

from __future__ import annotations

import re
from typing import Iterator

from .config import settings
from .retrieval import Hit

SYSTEM_PROMPT = """Você é o DocChat, um assistente que responde perguntas usando exclusivamente os \
trechos de documentos fornecidos como resultados de busca.

- Responda em português do Brasil, de forma direta e organizada (use listas quando ajudar).
- Baseie cada afirmação nos trechos; não invente valores, prazos ou regras.
- Se os trechos não trazem a resposta, diga claramente que não encontrou essa informação nos \
documentos e, se fizer sentido, sugira o que a pessoa pode procurar.
- Quando trechos diferentes se contradizem, aponte a divergência."""

Event = dict


def _blocks(text: str) -> list[dict]:
    """Cada parágrafo vira um bloco de texto: o Claude cita blocos inteiros, então blocos menores
    deixam as citações mais precisas."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [{"type": "text", "text": p} for p in parts] or [{"type": "text", "text": text.strip() or "(vazio)"}]


def build_search_results(hits: list[Hit]) -> list[dict]:
    results = []
    for hit in hits:
        title = hit.document_title + (f" — {hit.heading.split(' > ')[-1]}" if hit.heading else "")
        results.append(
            {
                "type": "search_result",
                "source": f"{hit.source}#trecho-{hit.chunk_id}",
                "title": title,
                "content": _blocks(hit.content),
                "citations": {"enabled": True},
            }
        )
    return results


def _retrieval_only(question: str, hits: list[Hit]) -> Iterator[Event]:
    if not hits:
        yield {"type": "text", "text": "Não encontrei nada relacionado nos documentos indexados."}
        return
    yield {
        "type": "text",
        "text": (
            "**Modo somente recuperação** (sem chave da API do Claude configurada). "
            "Estes são os trechos mais relevantes que encontrei:\n\n"
        ),
    }
    for index, hit in enumerate(hits[:3]):
        excerpt = re.sub(r"\s+", " ", hit.content).strip()
        if len(excerpt) > 320:
            excerpt = excerpt[:320].rsplit(" ", 1)[0] + "…"
        yield {"type": "text", "text": f"- {excerpt}"}
        yield {"type": "citation", "source_index": index, "cited_text": hit.content}
        yield {"type": "text", "text": "\n"}


def _claude(question: str, hits: list[Hit]) -> Iterator[Event]:
    import anthropic

    client = anthropic.Anthropic()
    content = [*build_search_results(hits), {"type": "text", "text": question}]
    try:
        with client.beta.messages.stream(
            model=settings.claude_model,
            max_tokens=64000,
            system=SYSTEM_PROMPT,
            output_config={"effort": settings.claude_effort},
            # se o modelo recusar por política de segurança, a API refaz a chamada no modelo de reserva
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": content}],
        ) as stream:
            for event in stream:
                if event.type != "content_block_delta":
                    continue
                if event.delta.type == "text_delta":
                    yield {"type": "text", "text": event.delta.text}
                elif event.delta.type == "citations_delta":
                    citation = event.delta.citation
                    if citation.type == "search_result_location":
                        yield {
                            "type": "citation",
                            "source_index": citation.search_result_index,
                            "cited_text": citation.cited_text,
                        }
            final = stream.get_final_message()
    except anthropic.AuthenticationError:
        yield {"type": "error", "message": "Chave da API do Claude inválida. Confira ANTHROPIC_API_KEY."}
        return
    except anthropic.RateLimitError:
        yield {"type": "error", "message": "Limite de uso da API atingido. Tente de novo em instantes."}
        return
    except anthropic.APIStatusError as exc:
        yield {"type": "error", "message": f"Erro da API do Claude ({exc.status_code}): {exc.message}"}
        return
    except anthropic.APIConnectionError:
        yield {"type": "error", "message": "Não consegui conectar na API do Claude. Verifique a internet."}
        return

    if final.stop_reason == "refusal":
        yield {"type": "error", "message": "O modelo recusou responder a esta pergunta."}
    elif final.stop_reason == "max_tokens":
        yield {"type": "text", "text": "\n\n_(resposta cortada pelo limite de tamanho)_"}
    yield {
        "type": "usage",
        "model": final.model,
        "input_tokens": final.usage.input_tokens,
        "output_tokens": final.usage.output_tokens,
    }


def answer(question: str, hits: list[Hit]) -> Iterator[Event]:
    if settings.llm_enabled and hits:
        yield from _claude(question, hits)
    else:
        yield from _retrieval_only(question, hits)
