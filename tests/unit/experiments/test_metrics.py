from pathlib import Path

import pytest

from medroute.domain.models import Solution
from medroute.experiments import (
    compare_solutions,
    extract_metrics,
    improvement_pct,
    summarize_solutions,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def solution():
    return Solution.model_validate_json(
        (ROOT / "tests/fixtures/solution_sp15.json").read_text(encoding="utf-8")
    )


def test_metricas_separam_duracao_total_maxima_e_unidades_de_violacao(solution):
    first = solution.routes[0].model_copy(
        update={"vehicle_id": "a", "sequence": ["e1"], "duracao_min": 10, "violacoes": {}}
    )
    second = first.model_copy(
        update={
            "vehicle_id": "b",
            "sequence": ["e2", "e3"],
            "duracao_min": 20,
            "violacoes": {"capacidade": 0.1, "autonomia": 2},
        }
    )
    empty = first.model_copy(update={"vehicle_id": "c", "sequence": [], "duracao_min": 99})
    sol = solution.model_copy(
        update={
            "routes": [first, second, empty],
            "penalidades": {"capacidade": 200, "autonomia": 40},
        }
    )
    original = sol.model_dump_json()
    metrics = extract_metrics(sol)
    assert metrics["duracao_total_min"] == 30
    assert metrics["duracao_max_min"] == 20
    assert metrics["veiculos_utilizados"] == 2
    assert metrics["entregas_atendidas"] == 3
    assert metrics["rotas_com_violacao"] == 1
    assert metrics["percentual_rotas_com_violacao"] == 50
    assert metrics["penalidade_total"] == 240
    assert sol.model_dump_json() == original


def test_sem_rotas_nao_divide_por_zero(solution):
    metrics = extract_metrics(solution.model_copy(update={"routes": []}))
    assert metrics["duracao_max_min"] == 0
    assert metrics["percentual_rotas_com_violacao"] == 0


@pytest.mark.parametrize(
    ("value", "reference", "expected"), [(80, 100, 20), (120, 100, -20), (100, 100, 0)]
)
def test_melhoria_percentual_positiva_significa_reducao(value, reference, expected):
    assert improvement_pct(value, reference) == pytest.approx(expected)


@pytest.mark.parametrize("value", [0, 10])
def test_referencia_zero_e_indefinida(value):
    assert improvement_pct(value, 0) is None


def test_comparacao_com_referencia_conhecida(solution):
    reference = solution.model_copy(
        update={
            "algoritmo": "nn",
            "fitness": 100,
            "custo_operacional": 80,
            "distancia_total_km": 40,
        }
    )
    better = reference.model_copy(
        update={"algoritmo": "ga", "fitness": 80, "custo_operacional": 60, "distancia_total_km": 20}
    )
    row = compare_solutions([better], reference)[0]
    assert row["referencia"] == "nn"
    assert row["fitness_melhoria_pct"] == 20
    assert row["custo_operacional_melhoria_pct"] == 25
    assert row["distancia_total_km_melhoria_pct"] == 50


def test_comparacao_rejeita_instancias_distintas(solution):
    other = solution.model_copy(update={"instance_nome": "outra"})
    with pytest.raises(ValueError, match="mesma instância"):
        compare_solutions([other], solution)


def test_resumo_calcula_desvio_amostral_e_agrupa_por_instancia_e_algoritmo(solution):
    first = solution.model_copy(update={"algoritmo": "ga", "fitness": 10, "seed": 1})
    second = first.model_copy(update={"fitness": 14, "seed": 2})
    baseline = first.model_copy(update={"algoritmo": "nn", "fitness": 20})
    other = first.model_copy(update={"instance_nome": "outra"})
    rows = summarize_solutions([first, second, baseline, other])
    assert len(rows) == 3
    ga = next(
        row
        for row in rows
        if row["instance_nome"] == solution.instance_nome and row["algoritmo"] == "ga"
    )
    assert ga["execucoes"] == 2
    assert ga["fitness_media"] == 12
    assert ga["fitness_dp"] == pytest.approx(8**0.5)
    assert ga["fitness_min"] == 10
    nn = next(row for row in rows if row["algoritmo"] == "nn")
    assert nn["fitness_dp"] == 0


def test_resumo_conta_execucoes_com_violacao(solution):
    clean = solution.model_copy(
        update={"routes": [route.model_copy(update={"violacoes": {}}) for route in solution.routes]}
    )
    violated_route = clean.routes[0].model_copy(update={"violacoes": {"autonomia": 1}})
    violated = clean.model_copy(update={"routes": [violated_route, *clean.routes[1:]]})
    assert summarize_solutions([clean, violated])[0]["percentual_execucoes_com_violacao"] == 50


def test_listas_vazias_retornam_listas_vazias(solution):
    assert summarize_solutions([]) == []
    assert compare_solutions([], solution) == []
