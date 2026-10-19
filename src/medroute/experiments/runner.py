"""Execução reproduzível de GA × baselines com o mesmo fitness e a mesma frota."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from medroute.baselines import (
    solve_nearest_neighbor,
    solve_nearest_neighbor_two_opt,
    solve_random,
    solve_savings,
)
from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.domain.models import Solution
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness

from .metrics import MetricRow, compare_solutions, summarize_solutions

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs/experimentos/s2.yaml"
BASELINES = (solve_nearest_neighbor, solve_nearest_neighbor_two_opt, solve_savings, solve_random)


class ExperimentConfig(BaseModel):
    """Caminhos no YAML são relativos ao próprio arquivo, não ao diretório de execução."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1)]
    instances: Annotated[list[Path], Field(min_length=1)]
    fleet: Path
    fitness: Path
    seeds: Annotated[list[int], Field(min_length=1)] = [7, 17, 42, 73, 101]
    ga_configs: Annotated[dict[str, GAConfig], Field(min_length=1)]
    vehicles: Annotated[list[str], Field(min_length=1)] | None = None
    two_opt_max_passes: Annotated[int, Field(ge=1)] = 100
    out: Path

    @model_validator(mode="after")
    def unique_runs(self) -> Self:
        for field in ("instances", "seeds", "vehicles"):
            values = getattr(self, field)
            if values is not None and len(set(values)) != len(values):
                raise ValueError(f"{field} não pode conter valores repetidos")
        if any(not name.strip() for name in self.ga_configs):
            raise ValueError("ga_configs exige nomes não vazios")
        return self


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    path = Path(path).resolve()
    try:
        config = ExperimentConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (ValueError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: configuração de experimento inválida: {error}") from error

    def resolve(value: Path) -> Path:
        return (path.parent / value).resolve()

    return config.model_copy(
        update={
            "instances": [resolve(value) for value in config.instances],
            **{field: resolve(getattr(config, field)) for field in ("fleet", "fitness", "out")},
        }
    )


@dataclass
class ExperimentResult:
    solutions: list[Solution]
    metrics: list[MetricRow]
    summary: list[MetricRow]
    metadata: dict


def run_experiment(
    config: ExperimentConfig, *, progress: Callable[[str], None] | None = None
) -> ExperimentResult:
    """Instância × seed × algoritmo. Cada GA tem motor/cache próprios por execução."""
    fleet = load_fleet(config.fleet)
    weights = load_fitness_config(config.fitness)
    instances = [load_instance(path, fleet) for path in config.instances]
    if len({inst.nome for inst in instances}) != len(instances):
        raise ValueError("as instâncias precisam ter nomes distintos para o resumo")
    if config.vehicles is not None:
        for inst in instances:
            unknown = set(config.vehicles) - {vehicle.id for vehicle in inst.fleet}
            if unknown:
                raise ValueError(f"veículos desconhecidos: {', '.join(sorted(unknown))}")
        instances = [
            inst.model_copy(
                update={
                    "fleet": [vehicle for vehicle in inst.fleet if vehicle.id in config.vehicles]
                }
            )
            for inst in instances
        ]

    source_root = Path(__file__).resolve().parents[1]
    inputs = [config.fleet, config.fitness, *config.instances]
    hashes = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    source_hashes = {
        str(path.relative_to(source_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_root.rglob("*.py"))
    }
    solutions: list[Solution] = []
    metrics: list[MetricRow] = []
    for inst in instances:
        dm = DistanceMatrix(inst, fleet)
        fitness_fn = make_fitness(inst, dm, fleet, weights)
        for seed in config.seeds:
            batch = []
            for solve in BASELINES:
                kwargs = (
                    {"max_passes": config.two_opt_max_passes}
                    if (solve is solve_nearest_neighbor_two_opt)
                    else {}
                )
                batch.append(solve(inst, dm, seed=seed, fitness_fn=fitness_fn, **kwargs))
            for name, ga_config in config.ga_configs.items():
                solution = GeneticAlgorithm(inst, dm, ga_config, fitness_fn).run(seed)
                batch.append(solution.model_copy(update={"algoritmo": f"ga_{name}"}))
            solutions.extend(batch)
            metrics.extend(compare_solutions(batch, reference=batch[0]))
            if progress is not None:
                progress(f"{inst.nome} · seed {seed}: {len(batch)} algoritmos concluídos")

    return ExperimentResult(
        solutions=solutions,
        metrics=metrics,
        summary=summarize_solutions(solutions),
        metadata={
            "schema_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "experiment": config.model_dump(mode="json"),
            "instances": [inst.model_dump(mode="json") for inst in instances],
            "fleet_config": yaml.safe_load(config.fleet.read_text(encoding="utf-8")),
            "fitness_config": weights.model_dump(mode="json"),
            "fitness": "definitivo: custo operacional + prioridade + penalidades P0/P1",
            "decoder": "split ótimo compartilhado; fallback guloso se não houver split hard viável",
            "duracao": "viagem + atendimento + retorno; trânsito com saída em inicio_jornada",
            "reference": "nearest_neighbor, mesma instância e seed",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "sha256_inputs": hashes,
            "sha256_source": source_hashes,
        },
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_results(result: ExperimentResult, out: str | Path) -> Path:
    """Exporta soluções, métricas, resumo, histórico por passo/geração e proveniência."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / "metrics.csv", result.metrics)
    _write_csv(out / "summary.csv", result.summary)
    history = [
        {
            "instance_nome": solution.instance_nome,
            "algoritmo": solution.algoritmo,
            "seed": solution.seed,
            "passo": step,
            "fitness": value,
        }
        for solution in result.solutions
        for step, value in enumerate(solution.historico_fitness)
    ]
    _write_csv(out / "convergence.csv", history)
    for filename, data in (
        ("solutions.json", [solution.model_dump(mode="json") for solution in result.solutions]),
        ("metadata.json", result.metadata),
    ):
        (out / filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return out.resolve()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, help="Sobrescreve o destino do YAML.")
    parser.add_argument("--seeds", type=int, nargs="+", help="Sobrescreve as seeds do YAML.")
    args = parser.parse_args(argv)
    try:
        config = load_experiment_config(args.config)
        updates = {}
        if args.out is not None:
            updates["out"] = args.out.resolve()
        if args.seeds is not None:
            updates["seeds"] = args.seeds
        config = ExperimentConfig.model_validate({**config.model_dump(), **updates})
        result = run_experiment(config, progress=print)
        destination = write_results(result, config.out)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print("Instância  Algoritmo                         Fitness (R$), média ± dp")
    for row in result.summary:
        print(
            f"{row['instance_nome']:<11}{row['algoritmo']:<34}"
            f"{row['fitness_media']:>10.2f} ± {row['fitness_dp']:.2f}"
        )
    print(f"Resultados: {destination}")


if __name__ == "__main__":
    main()
