"""Fitness PROVISÓRIO até a Spec 03 ser aprovada e `constraints/` chegar (14/10).

fitness = custo_operacional + Σ violação × peso. Ainda sem custo de prioridade (tempo de
chegada) e com os pesos propostos na Spec 03, seção 4, fixos aqui em vez de configuração.
"""

from __future__ import annotations

from medroute.domain.models import Route

PENALTY_WEIGHTS: dict[str, float] = {
    "capacidade": 2000.0,  # R$ por 100 % de excesso
    "autonomia": 20.0,  # R$ por km acima da autonomia
    "compatibilidade": 1000.0,  # R$ por entrega incompatível
}


def penalties(routes: list[Route]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for route in routes:
        for key, amount in route.violacoes.items():
            totals[key] = totals.get(key, 0.0) + amount * PENALTY_WEIGHTS.get(key, 0.0)
    return totals


def evaluate(routes: list[Route]) -> float:
    return sum(route.custo for route in routes) + sum(penalties(routes).values())
