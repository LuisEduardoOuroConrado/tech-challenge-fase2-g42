import pytest
from conftest import make_instance
from pydantic import ValidationError

from medroute.data import DistanceMatrix
from medroute.ga import GAConfig, GeneticAlgorithm


def config(**overrides) -> GAConfig:
    data = {
        "population_size": 20,
        "generations": 30,
        "crossover_rate": 0.9,
        "mutation_rate": 0.2,
        "elitism": 2,
        "tournament_size": 3,
        "crossover": "ox",
        "mutation": "inversion",
    }
    data.update(overrides)
    return GAConfig(**data)


@pytest.fixture
def inst():
    return make_instance(10)


def run(inst, seed=1, **overrides):
    return GeneticAlgorithm(inst, DistanceMatrix(inst), config(**overrides)).run(seed)


def test_mesmo_seed_mesma_solucao(inst):
    a, b = run(inst), run(inst)
    assert a.model_dump(exclude={"tempo_exec_s"}) == b.model_dump(exclude={"tempo_exec_s"})


@pytest.mark.parametrize("crossover", ["ox", "pmx"])
@pytest.mark.parametrize("mutation", ["swap", "inversion", "two_opt"])
def test_elitismo_nunca_piora_o_historico(inst, crossover, mutation):
    history = run(inst, crossover=crossover, mutation=mutation).historico_fitness
    assert all(nxt <= cur for cur, nxt in zip(history, history[1:], strict=False))


def test_ga_melhora_a_populacao_inicial(inst):
    solution = run(inst, generations=60)
    assert solution.fitness < solution.historico_fitness[0]


def test_para_no_limite_de_geracoes(inst):
    assert len(run(inst, generations=7).historico_fitness) == 7


def test_para_por_estagnacao(inst):
    solution = run(inst, generations=200, patience=5, crossover_rate=0.0, mutation_rate=0.0)
    assert len(solution.historico_fitness) < 200


@pytest.mark.parametrize("rate", [0.0, 1.0])
def test_taxas_nos_extremos(inst, rate):
    solution = run(inst, crossover_rate=rate, mutation_rate=rate)
    assert len(solution.historico_fitness) == 30


def test_solution_preenchida(inst):
    solution = run(inst, seed=42)
    assert solution.seed == 42
    assert solution.algoritmo == "ga"
    assert solution.instance_nome == inst.nome
    assert solution.tempo_exec_s > 0
    assert solution.fitness == pytest.approx(min(solution.historico_fitness))
    assert solution.custo_operacional == pytest.approx(sum(r.custo for r in solution.routes))
    assert solution.distancia_total_km == pytest.approx(
        sum(r.distancia_km for r in solution.routes)
    )
    assert sorted(i for r in solution.routes for i in r.sequence) == [d.id for d in inst.deliveries]


@pytest.mark.parametrize(
    "overrides",
    [
        {"population_size": 1, "tournament_size": 1},
        {"elitism": 20},
        {"tournament_size": 21},
        {"tournament_size": 1},
        {"crossover_rate": 1.5},
        {"mutation_rate": -0.1},
        {"generations": 0},
        {"patience": 0},
        {"crossover": "cx"},
    ],
)
def test_config_invalida(overrides):
    with pytest.raises(ValidationError):
        config(**overrides)
