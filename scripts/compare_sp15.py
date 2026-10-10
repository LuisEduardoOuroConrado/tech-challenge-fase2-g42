"""Comparação inicial da S1, com parâmetros fixos e resultados reproduzíveis."""

import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

from medroute.baselines import (
    solve_nearest_neighbor,
    solve_nearest_neighbor_two_opt,
    solve_random,
)
from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.experiments import compare_solutions, summarize_solutions
from medroute.ga import GAConfig, GeneticAlgorithm

ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 17, 42, 73, 101])
    parser.add_argument("--veiculo", default="van-01")
    parser.add_argument("--out", type=Path, default=ROOT / "data/resultados/comparativo_s1")
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("as seeds não podem se repetir")

    fleet = load_fleet(ROOT / "configs/frota.yaml")
    inst = load_instance(ROOT / "data/instances/sp_15.json", fleet)
    selected = [vehicle for vehicle in inst.fleet if vehicle.id == args.veiculo]
    if not selected:
        parser.error(f"veículo desconhecido: {args.veiculo}")
    inst = inst.model_copy(update={"fleet": selected})
    dm = DistanceMatrix(inst, fleet)
    config = GAConfig(
        population_size=80,
        generations=200,
        crossover_rate=0.9,
        mutation_rate=0.2,
        elitism=2,
        tournament_size=3,
        crossover="ox",
        mutation="inversion",
    )
    solutions, rows = [], []
    for seed in args.seeds:
        nn = solve_nearest_neighbor(inst, dm, seed=seed)
        batch = [
            nn,
            solve_nearest_neighbor_two_opt(inst, dm, seed=seed),
            solve_random(inst, dm, seed=seed),
            GeneticAlgorithm(inst, dm, config).run(seed=seed),
        ]
        solutions.extend(batch)
        rows.extend(compare_solutions(batch, reference=nn))
    summaries = summarize_solutions(solutions)

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "metrics.csv", rows)
    write_csv(args.out / "summary.csv", summaries)
    (args.out / "solutions.json").write_text(
        json.dumps([solution.model_dump(mode="json") for solution in solutions], indent=2) + "\n",
        encoding="utf-8",
    )
    inputs = [
        "scripts/compare_sp15.py",
        "data/instances/sp_15.json",
        "configs/frota.yaml",
        "src/medroute/data/distance.py",
        "src/medroute/data/fleet.py",
        "src/medroute/data/loader.py",
        "src/medroute/domain/models.py",
        "src/medroute/ga/fitness.py",
        "src/medroute/ga/decoder.py",
        "src/medroute/ga/encoding.py",
        "src/medroute/ga/engine.py",
        "src/medroute/ga/operators.py",
        "src/medroute/baselines/nearest_neighbor.py",
        "src/medroute/baselines/two_opt.py",
        "src/medroute/baselines/random.py",
        "src/medroute/baselines/_common.py",
        "src/medroute/experiments/metrics.py",
    ]
    metadata = {
        "instance_nome": inst.nome,
        "vehicle": selected[0].model_dump(mode="json"),
        "seeds": args.seeds,
        "ga_config": config.model_dump(),
        "two_opt_max_passes": 100,
        "fitness": "provisório: custo operacional + penalidades; sem custo de prioridade",
        "duracao": "tempo de viagem informado pelo decoder; sem tempo de serviço",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in inputs},
    }
    (args.out / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Algoritmo                     Fitness (R$), média ± dp       Km, média")
    for row in summaries:
        print(
            f"{row['algoritmo']:<30}"
            f"{row['fitness_media']:>10.2f} ± {row['fitness_dp']:<10.2f}"
            f"{row['distancia_total_km_media']:>10.2f}"
        )
    print(f"Resultados: {args.out.resolve()}")


if __name__ == "__main__":
    main()
