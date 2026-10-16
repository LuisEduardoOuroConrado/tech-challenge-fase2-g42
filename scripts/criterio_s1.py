"""Critério da S1 "GA vence NN e NN+2-opt" com o fitness definitivo (Spec 03).

Diferente de `compare_sp15.py` (fitness provisório, decoder guloso), aqui NN e NN+2-opt são
avaliados com o mesmo split ótimo, `FleetConfig` e fitness do GA; o 2-opt também otimiza esse
fitness. Compara GA puro e GA híbrido (semente NN + busca local) em dois cenários: só a van
(TSP) e a frota completa.

    python scripts/criterio_s1.py --inst sp_15
    python scripts/criterio_s1.py --inst sp_40 --seeds 7 17 --csv results/criterio_sp40.csv
"""

import argparse
import csv
from pathlib import Path

from medroute.baselines.nearest_neighbor import nearest_neighbor_order
from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness
from medroute.ga.decoder import split_decode
from medroute.ga.operators import two_opt_local

ROOT = Path(__file__).resolve().parents[1]
SEEDS = [7, 17, 42, 73, 101]  # as mesmas de reports/secoes/pedro-baselines-s1.md
BASE = {
    "population_size": 100,
    "generations": 300,
    "crossover_rate": 0.9,
    "mutation_rate": 0.2,
    "elitism": 2,
    "tournament_size": 3,
    "crossover": "ox",
    "mutation": "inversion",
}
VARIANTES = {
    "ga_puro": {},
    "ga_hibrido": {"seed_nearest_neighbor": True, "local_search_rate": 0.3},
}
TOLERANCIA = 1e-6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inst", default="sp_15")
    parser.add_argument("--van", default="van-01", help="Veículo do cenário TSP.")
    parser.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    parser.add_argument("--csv", type=Path, help="Grava uma linha por (cenário, algoritmo, seed).")
    args = parser.parse_args()

    fleet = load_fleet(ROOT / "configs" / "frota.yaml")
    cfg = load_fitness_config(ROOT / "configs" / "fitness.yaml")
    full = load_instance(ROOT / "data" / "instances" / f"{args.inst}.json", fleet)
    van = [vehicle for vehicle in full.fleet if vehicle.id == args.van]
    cenarios = {"tsp_van": full.model_copy(update={"fleet": van}), "frota": full}

    rows = []
    for cenario, inst in cenarios.items():
        dm = DistanceMatrix(inst, fleet)
        fitness_fn = make_fitness(inst, dm, fleet, cfg)

        def score(chromosome, inst=inst, dm=dm, fitness_fn=fitness_fn):
            routes = split_decode(chromosome, inst, dm, cfg, fitness_fn.servico_min, fleet)
            return fitness_fn(routes)

        nn = nearest_neighbor_order(inst, dm)
        ref = {"nn": score(nn), "nn_2opt": score(two_opt_local(nn, score))}
        print(
            f"== {args.inst} | {cenario}: NN R$ {ref['nn']:.2f} | NN+2-opt R$ {ref['nn_2opt']:.2f}"
        )
        for nome, extra in VARIANTES.items():
            config = GAConfig(**BASE, **extra)
            valores = []
            for seed in args.seeds:
                solution = GeneticAlgorithm(inst, dm, config, fitness_fn).run(seed)
                valores.append(solution.fitness)
                rows.append(
                    {
                        "instancia": args.inst,
                        "cenario": cenario,
                        "algoritmo": nome,
                        "seed": seed,
                        "fitness": round(solution.fitness, 2),
                        "nn": round(ref["nn"], 2),
                        "nn_2opt": round(ref["nn_2opt"], 2),
                        "tempo_s": round(solution.tempo_exec_s, 1),
                    }
                )
            vence_nn = sum(v < ref["nn"] - TOLERANCIA for v in valores)
            vence = sum(v < ref["nn_2opt"] - TOLERANCIA for v in valores)
            empata = sum(abs(v - ref["nn_2opt"]) <= TOLERANCIA for v in valores)
            n = len(valores)
            print(
                f"  {nome}: "
                + " | ".join(f"{v:.2f}" for v in valores)
                + f"\n    vence NN {vence_nn}/{n} | NN+2-opt: vence {vence}, empata {empata},"
                f" perde {n - vence - empata}"
            )

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV: {args.csv}")


if __name__ == "__main__":
    main()
