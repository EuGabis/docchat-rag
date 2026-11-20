"""Avaliação da recuperação: compara busca vetorial, por palavra-chave e híbrida.

Para cada pergunta sabemos qual seção contém a resposta. Medimos:
- Hit@3: a seção certa apareceu entre os 3 primeiros trechos?
- MRR: média de 1/posição do primeiro trecho correto (1.0 = sempre em primeiro).

Rode depois de `python scripts/seed.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval import search  # noqa: E402

# (pergunta, trecho que precisa aparecer no título da seção)
GOLDEN = [
    ("Quanto custa o curso de Piloto Privado completo?", "Piloto Privado"),
    ("Qual a idade mínima para fazer piloto comercial?", "Piloto Comercial"),
    ("Comissário de voo precisa saber nadar?", "Comissário de Voo"),
    ("Onde acontece o estágio do curso de mecânico?", "Mecânico de Manutenção"),
    ("Quais papéis preciso levar para me inscrever?", "Documentos obrigatórios"),
    ("Menor de idade pode se matricular?", "Documentos obrigatórios"),
    ("A escola faz o exame médico?", "Certificado médico"),
    ("Até quando posso mandar os documentos digitalizados?", "Prazo para entregar documentos"),
    ("Quantas faltas posso ter nas aulas teóricas?", "Frequência"),
    ("Desmarquei o voo em cima da hora, vou pagar?", "Aulas práticas de voo"),
    ("Se eu desistir do curso recebo meu dinheiro de volta?", "Cancelamento e reembolso"),
    ("Posso beber cerveja na noite antes do voo?", "Conduta"),
    ("Tem desconto para pagamento no Pix?", "Formas de pagamento"),
    ("Existe bolsa de estudos?", "Bolsas e descontos"),
    ("Como emitir 2ª via do boleto?", "Segunda via de boleto"),
    ("Esqueci a senha do portal, o que faço?", "Portal do Aluno"),
]


def evaluate(mode: str, k: int = 3) -> tuple[float, float]:
    hits_at_k, reciprocal = 0, 0.0
    for question, expected in GOLDEN:
        results = search(question, top_k=10, mode=mode)
        rank = next((i for i, h in enumerate(results, start=1) if expected in h.heading), None)
        if rank and rank <= k:
            hits_at_k += 1
        if rank:
            reciprocal += 1 / rank
    n = len(GOLDEN)
    return hits_at_k / n, reciprocal / n


def main() -> None:
    print(f"{len(GOLDEN)} perguntas\n")
    print(f"{'modo':<12} {'Hit@3':>7} {'MRR':>7}")
    for mode in ("keyword", "vector", "hybrid"):
        hit, mrr = evaluate(mode)
        print(f"{mode:<12} {hit:>7.0%} {mrr:>7.3f}")


if __name__ == "__main__":
    main()
