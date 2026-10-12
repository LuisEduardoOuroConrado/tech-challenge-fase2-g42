import json
from pathlib import Path

from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.domain.models import Solution
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness

ROOT = Path(__file__).resolve().parents[2]


def test_ga_resolve_sp15_e_serializa_no_formato_da_fixture():
    fleet = load_fleet(ROOT / "configs" / "frota.yaml")
    inst = load_instance(ROOT / "data" / "instances" / "sp_15.json", fleet)
    config = GAConfig(
        population_size=30,
        generations=40,
        crossover_rate=0.9,
        mutation_rate=0.2,
        elitism=2,
        tournament_size=3,
        crossover="ox",
        mutation="inversion",
    )
    solution = GeneticAlgorithm(inst, DistanceMatrix(inst, fleet), config).run(seed=17)

    restored = Solution.model_validate_json(solution.model_dump_json())
    assert restored == solution
    assert sorted(i for r in solution.routes for i in r.sequence) == sorted(
        d.id for d in inst.deliveries
    )
    assert sum(solution.penalidades.values()) == 0

    fixture = json.loads((ROOT / "tests" / "fixtures" / "solution_sp15.json").read_text("utf-8"))
    serialized = json.loads(solution.model_dump_json())
    assert serialized.keys() == fixture.keys()
    assert serialized["routes"][0].keys() == fixture["routes"][0].keys()
    assert serialized["routes"][0]["violacoes"].keys() <= fixture["routes"][0]["violacoes"].keys()


def test_fitness_definitivo_em_sp40_usa_a_frota_sem_violacao_hard():
    """Spec 03, seção 8: GA em sp_40 com o fitness definitivo, sem violação hard."""
    fleet = load_fleet(ROOT / "configs" / "frota.yaml")
    inst = load_instance(ROOT / "data" / "instances" / "sp_40.json", fleet)
    dm = DistanceMatrix(inst, fleet)
    fitness_fn = make_fitness(
        inst, dm, fleet, load_fitness_config(ROOT / "configs" / "fitness.yaml")
    )
    config = GAConfig(
        population_size=20,
        generations=15,
        crossover_rate=0.9,
        mutation_rate=0.2,
        elitism=2,
        tournament_size=3,
        crossover="ox",
        mutation="inversion",
    )
    solution = GeneticAlgorithm(inst, dm, config, fitness_fn).run(seed=7)

    assert sum(solution.penalidades.values()) == 0
    assert len(solution.routes) > 1  # a van sozinha comporta tudo; o split ótimo divide
    assert sorted(i for r in solution.routes for i in r.sequence) == sorted(
        d.id for d in inst.deliveries
    )
