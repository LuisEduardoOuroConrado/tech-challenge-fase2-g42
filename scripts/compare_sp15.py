"""Comparativo S1 atualizado: GA puro/híbrido × quatro baselines, fitness definitivo."""

import argparse
from pathlib import Path

from medroute.experiments.runner import (
    ExperimentConfig,
    load_experiment_config,
    run_experiment,
    write_results,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 17, 42, 73, 101])
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument("--veiculo", default="van-01")
    scenario.add_argument("--frota-completa", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    config = load_experiment_config(ROOT / "configs/experimentos/s1_atualizado.yaml")
    updates = {
        "seeds": args.seeds,
        "vehicles": None if args.frota_completa else [args.veiculo],
    }
    if args.out is not None:
        updates["out"] = args.out.resolve()
    elif args.frota_completa:
        updates["out"] = ROOT / "data/resultados/comparativo_s1_frota_atualizado"
    try:
        config = ExperimentConfig.model_validate({**config.model_dump(), **updates})
        result = run_experiment(config, progress=print)
        out = write_results(result, config.out)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for row in result.summary:
        print(f"{row['algoritmo']:<32} R$ {row['fitness_media']:.2f} ± {row['fitness_dp']:.2f}")
    print(f"Resultados: {out}")


if __name__ == "__main__":
    main()
