from pathlib import Path

from medroute.baselines import (
    solve_nearest_neighbor,
    solve_nearest_neighbor_two_opt,
    solve_random,
)
from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.domain.models import Solution
from medroute.experiments import compare_solutions

ROOT = Path(__file__).resolve().parents[2]


def test_baselines_sp15_tsp_geram_solucoes_viaveis_comparaveis():
    fleet = load_fleet(ROOT / "configs/frota.yaml")
    inst = load_instance(ROOT / "data/instances/sp_15.json", fleet)
    inst = inst.model_copy(update={"fleet": [v for v in inst.fleet if v.id == "van-01"]})
    dm = DistanceMatrix(inst, fleet)
    solutions = [
        solve(inst, dm, seed=7)
        for solve in [solve_nearest_neighbor, solve_nearest_neighbor_two_opt, solve_random]
    ]
    nn, improved, _ = solutions
    assert improved.fitness <= nn.fitness
    expected = sorted(delivery.id for delivery in inst.deliveries)
    for solution in solutions:
        assert len(solution.routes) == 1
        assert sorted(solution.routes[0].sequence) == expected
        assert not any(solution.routes[0].violacoes.values())
        assert solution.distancia_total_km <= inst.fleet[0].autonomia_km
        assert Solution.model_validate_json(solution.model_dump_json()) == solution
    rows = compare_solutions(solutions, reference=nn)
    assert rows[0]["fitness_melhoria_pct"] == 0
    assert rows[1]["fitness_melhoria_pct"] >= 0
