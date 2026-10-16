from pathlib import Path

import pytest

from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.experiments.runner import load_experiment_config, run_experiment, write_results
from medroute.ga import load_fitness_config, make_fitness
from medroute.llm import MockClient, generate_report
from medroute.viz.map import build_map

ROOT = Path(__file__).resolve().parents[2]


def test_runner_sp40_integra_baselines_ga_metricas_mapa_e_relatorio_mock(tmp_path):
    config = load_experiment_config(ROOT / "configs/experimentos/s2.yaml")
    config = config.model_copy(
        update={
            "instances": [ROOT / "data/instances/sp_40.json"],
            "seeds": [7],
            "ga_configs": {
                name: value.model_copy(update={"population_size": 4, "generations": 2})
                for name, value in config.ga_configs.items()
            },
        }
    )
    result = run_experiment(config)
    assert len(result.solutions) == 7
    fleet = load_fleet(config.fleet)
    inst = load_instance(config.instances[0], fleet)
    dm = DistanceMatrix(inst, fleet)
    fitness_fn = make_fitness(inst, dm, fleet, load_fitness_config(config.fitness))
    expected = sorted(delivery.id for delivery in inst.deliveries)
    for solution in result.solutions:
        assert sorted(stop for route in solution.routes for stop in route.sequence) == expected
        assert solution.fitness == pytest.approx(fitness_fn(solution.routes))
        assert solution.penalidades == fitness_fn.penalties(solution.routes)
    savings = next(solution for solution in result.solutions if solution.algoritmo == "savings")
    assert all(
        not route.violacoes[key]
        for route in savings.routes
        for key in ("capacidade", "autonomia", "compatibilidade")
    )
    out = write_results(result, tmp_path)
    assert (out / "summary.csv").is_file()
    html = build_map(savings, inst).get_root().render()
    assert all(route.vehicle_id in html for route in savings.routes)
    # A API de relatório consome Solutions dos baselines e configurações do GA.
    report = generate_report(result.solutions, inst, "diario", MockClient())
    assert isinstance(report, str) and report.strip()
