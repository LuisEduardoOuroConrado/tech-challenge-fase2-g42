import json
from pathlib import Path

from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.domain.models import Solution
from medroute.ga import GAConfig, GeneticAlgorithm

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
