from app.generation import _retrieval_only, build_search_results
from app.retrieval import Hit, rrf_fuse


def make_hit(cid: int, content: str = "Primeiro parágrafo.\n\nSegundo parágrafo.") -> Hit:
    return Hit(cid, 1, "Catálogo de Cursos", "cursos.md", "Catálogo > Piloto Privado", content)


def test_rrf_rewards_items_present_in_both_lists():
    scores = rrf_fuse([[1, 2, 3], [3, 4]], k=60)
    assert scores[3] > scores[1]  # 3 aparece nas duas listas
    assert scores[1] > scores[2]
    assert scores[2] == scores[4]  # mesma posição (2ª) em listas diferentes empata
    assert abs(scores[1] - 1 / 61) < 1e-12


def test_rrf_with_single_list_preserves_order():
    scores = rrf_fuse([[10, 20, 30]])
    assert sorted(scores, key=scores.get, reverse=True) == [10, 20, 30]


def test_search_results_follow_api_schema():
    [result] = build_search_results([make_hit(7)])
    assert result["type"] == "search_result"
    assert result["source"] == "cursos.md#trecho-7"
    assert result["title"] == "Catálogo de Cursos — Piloto Privado"
    assert result["citations"] == {"enabled": True}
    # cada parágrafo vira um bloco de texto (citações mais precisas)
    assert [b["text"] for b in result["content"]] == ["Primeiro parágrafo.", "Segundo parágrafo."]


def test_retrieval_only_mode_cites_top_three():
    events = list(_retrieval_only("pergunta", [make_hit(i) for i in range(5)]))
    cites = [e for e in events if e["type"] == "citation"]
    assert [c["source_index"] for c in cites] == [0, 1, 2]


def test_retrieval_only_without_hits():
    events = list(_retrieval_only("pergunta", []))
    assert events == [{"type": "text", "text": "Não encontrei nada relacionado nos documentos indexados."}]
