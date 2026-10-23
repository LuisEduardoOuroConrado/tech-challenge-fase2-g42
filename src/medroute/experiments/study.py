"""Matriz E1–E6 com execuções deduplicadas, retomada e validação dos resultados."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from medroute.baselines import (
    solve_nearest_neighbor,
    solve_nearest_neighbor_two_opt,
    solve_random,
    solve_savings,
)
from medroute.constraints import (
    cronograma_rota,
    duracao_rota,
    violacao_autonomia,
    violacao_capacidade,
    violacao_compatibilidade,
    violacao_deadline,
    violacao_jornada,
)
from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.domain.models import Instance, Solution
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness
from medroute.ga.fitness import Fitness, FitnessConfig

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "configs/experimentos/s3.yaml"
BASELINES = {
    "nearest_neighbor": solve_nearest_neighbor,
    "nearest_neighbor_two_opt": solve_nearest_neighbor_two_opt,
    "savings": solve_savings,
    "random": solve_random,
}


class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ga: dict[str, Any] = Field(default_factory=dict)
    priority_scale: Annotated[float, Field(ge=0)] = 1.0


class Experiment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    variants: Annotated[dict[str, Variant], Field(min_length=1)]
    baselines: bool = False
    reference: str | None = None


class StudyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    instances: Annotated[list[Path], Field(min_length=1)]
    fleet: Path
    fitness: Path
    seeds: Annotated[list[int], Field(min_length=1)]
    base_ga: GAConfig
    experiments: Annotated[dict[str, Experiment], Field(min_length=1)]
    two_opt_max_passes: Annotated[int, Field(ge=1)] = 100
    out: Path
    cache: Path
    figures: Path

    @model_validator(mode="after")
    def check_design(self):
        for field in ("instances", "seeds"):
            values = getattr(self, field)
            if len(values) != len(set(values)):
                raise ValueError(f"{field} não pode conter valores repetidos")
        for experiment in self.experiments.values():
            names = set(experiment.variants) | (set(BASELINES) if experiment.baselines else set())
            if experiment.reference is not None and experiment.reference not in names:
                raise ValueError("referência desconhecida")
            for variant in experiment.variants.values():
                GAConfig.model_validate({**self.base_ga.model_dump(), **variant.ga})
        return self


def load_study_config(path: str | Path = DEFAULT_CONFIG) -> StudyConfig:
    path = Path(path).resolve()
    config = StudyConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return config.model_copy(
        update={
            "instances": [(path.parent / value).resolve() for value in config.instances],
            **{
                field: (path.parent / getattr(config, field)).resolve()
                for field in ("fleet", "fitness", "out", "cache", "figures")
            },
        }
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_hashes() -> dict[str, str]:
    """Fontes que definem o resultado; renderização e textos não invalidam o cache."""
    source = Path(__file__).resolve().parents[1]
    paths = []
    for directory in ("domain", "data", "ga", "constraints", "baselines"):
        paths.extend((source / directory).rglob("*.py"))
    return {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def scaled_weights(weights: FitnessConfig, scale: float) -> FitnessConfig:
    data = weights.model_dump()
    data["prioridade_rs_min"] = {p: value * scale for p, value in weights.prioridade_rs_min.items()}
    return FitnessConfig.model_validate(data)


def build_design(config: StudyConfig) -> tuple[dict[str, dict], list[dict]]:
    """Uma receita por algoritmo/instância/seed/pesos; a referência pode servir vários E."""
    hashes = source_hashes()
    inputs = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [config.fleet, config.fitness, *config.instances]
    }
    jobs, design = {}, []
    names = [load_instance(path).nome for path in config.instances]
    if len(names) != len(set(names)):
        raise ValueError("instâncias precisam de nomes distintos")
    for experiment_id, experiment in config.experiments.items():
        variants = [(name, "ga", variant) for name, variant in experiment.variants.items()]
        if experiment.baselines:
            if set(experiment.variants) & set(BASELINES):
                raise ValueError("nome de variante colide com baseline")
            variants.extend((name, name, Variant()) for name in BASELINES)
        for name, algorithm, variant in variants:
            ga = GAConfig.model_validate({**config.base_ga.model_dump(), **variant.ga})
            for path, instance_name in zip(config.instances, names, strict=True):
                for seed in config.seeds:
                    recipe = {
                        "instance": str(path),
                        "fleet": str(config.fleet),
                        "fitness": str(config.fitness),
                        "seed": seed,
                        "algorithm": algorithm,
                        "ga": ga.model_dump(mode="json") if algorithm == "ga" else None,
                        "priority_scale": variant.priority_scale,
                        "two_opt_max_passes": config.two_opt_max_passes,
                        "inputs": {
                            str(p): inputs[str(p)] for p in (path, config.fleet, config.fitness)
                        },
                        "sources": hashes,
                        "python": platform.python_version(),
                    }
                    job_id = _hash(recipe)
                    jobs[job_id] = recipe
                    design.append(
                        {
                            "experiment": experiment_id,
                            "configuration": name,
                            "instance_nome": instance_name,
                            "seed": seed,
                            "job_id": job_id,
                        }
                    )
    return jobs, design


def _close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-7):
        raise ValueError(f"{label}: {actual} != {expected}")


def validate_solution(solution: Solution, inst: Instance, dm: DistanceMatrix, fn: Fitness) -> None:
    """Recalcula sem confiar nas métricas/violações gravadas pelo otimizador."""
    if solution.instance_nome != inst.nome:
        raise ValueError("instância da solução divergente")
    stops = [stop for route in solution.routes for stop in route.sequence]
    if sorted(stops) != sorted(delivery.id for delivery in inst.deliveries):
        raise ValueError("cobertura de entregas divergente")
    vehicles = {vehicle.id: vehicle for vehicle in inst.fleet}
    deliveries = {delivery.id: delivery for delivery in inst.deliveries}
    index = {delivery.id: i for i, delivery in enumerate(inst.deliveries, 1)}
    for route in solution.routes:
        if route.vehicle_id not in vehicles or not route.sequence:
            raise ValueError("rota vazia ou veículo desconhecido")
        vehicle = vehicles[route.vehicle_id]
        cargo = [deliveries[stop] for stop in route.sequence]
        km = dm.route_km([index[stop] for stop in route.sequence])
        duration = duracao_rota(dm, vehicle, route.sequence, inst, fn.fleet, fn.fleet.saida_min)
        arrivals = cronograma_rota(dm, vehicle, route.sequence, inst, fn.fleet, fn.fleet.saida_min)
        for field, value in {
            "distancia_km": km,
            "duracao_min": duration,
            "carga_kg": sum(d.peso_kg for d in cargo),
            "carga_l": sum(d.volume_l for d in cargo),
            "custo": vehicle.custo_fixo + vehicle.custo_km * km,
        }.items():
            _close(getattr(route, field), value, field)
        # A base 86276b9 conta atributos incompatíveis, incluindo duas vezes uma
        # entrega refrigerada E volumosa na moto. Preservar o objetivo observado
        # na rodada e auditar separadamente a contagem de entregas no relatório.
        overlaps = sum(
            d.refrigerado
            and not vehicle.aceita_refrigerado
            and d.volume_l > fn.fleet.volumoso_limiar_l
            and vehicle.tipo.value in fn.fleet.tipos_sem_volumoso
            for d in cargo
        )
        violations = {
            "capacidade": violacao_capacidade(vehicle, cargo),
            "autonomia": violacao_autonomia(vehicle, km),
            "compatibilidade": violacao_compatibilidade(fn.fleet, vehicle, cargo) + overlaps,
            "deadline": violacao_deadline(arrivals, cargo),
            "jornada": violacao_jornada(duration, fn.fleet),
        }
        if route.violacoes.keys() != violations.keys():
            raise ValueError("chaves de violação divergentes")
        for key, value in violations.items():
            _close(route.violacoes[key], value, key)
    _close(solution.fitness, fn(solution.routes), "fitness")
    _close(solution.custo_operacional, sum(r.custo for r in solution.routes), "custo")
    _close(solution.distancia_total_km, sum(r.distancia_km for r in solution.routes), "distância")
    penalties = fn.penalties(solution.routes)
    if solution.penalidades.keys() != penalties.keys():
        raise ValueError("chaves de penalidade divergentes")
    for key, value in penalties.items():
        _close(solution.penalidades[key], value, f"penalidade {key}")
    if solution.historico_fitness:
        _close(solution.historico_fitness[-1], solution.fitness, "último ponto da curva")
        if any(
            b > a + 1e-7
            for a, b in zip(
                solution.historico_fitness, solution.historico_fitness[1:], strict=False
            )
        ):
            raise ValueError("curva de melhor fitness não é monótona")


def _context(recipe: dict):
    fleet = load_fleet(recipe["fleet"])
    inst = load_instance(recipe["instance"], fleet)
    dm = DistanceMatrix(inst, fleet)
    weights = load_fitness_config(recipe["fitness"])
    fn = make_fitness(inst, dm, fleet, scaled_weights(weights, recipe["priority_scale"]))
    return inst, dm, fn


def _execute(recipe: dict) -> dict:
    inst, dm, fn = _context(recipe)
    if recipe["algorithm"] == "ga":
        solution = GeneticAlgorithm(inst, dm, GAConfig.model_validate(recipe["ga"]), fn).run(
            recipe["seed"]
        )
    else:
        kwargs = (
            {"max_passes": recipe["two_opt_max_passes"]}
            if recipe["algorithm"] == "nearest_neighbor_two_opt"
            else {}
        )
        solution = BASELINES[recipe["algorithm"]](
            inst, dm, seed=recipe["seed"], fitness_fn=fn, **kwargs
        )
    validate_solution(solution, inst, dm, fn)
    return solution.model_dump(mode="json")


def run_study(
    config: StudyConfig, *, workers: int = 1, progress: Callable[[str], None] = print
) -> tuple[dict, list[dict], dict]:
    if workers < 1:
        raise ValueError("workers deve ser >= 1")
    jobs, design = build_design(config)
    config.cache.mkdir(parents=True, exist_ok=True)
    solutions, pending = {}, {}
    for job_id, recipe in jobs.items():
        path = config.cache / f"{job_id}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["recipe"] != recipe or record["solution_sha256"] != _hash(record["solution"]):
                raise ValueError(f"cache corrompido: {path}")
            solution = Solution.model_validate(record["solution"])
            inst, dm, fn = _context(recipe)
            validate_solution(solution, inst, dm, fn)
            solutions[job_id] = record["solution"]
        else:
            pending[job_id] = recipe
    progress(
        f"{len(design)} observações; {len(jobs)} execuções únicas; "
        f"{len(solutions)} recuperadas; {len(pending)} pendentes"
    )

    def save(job_id, data):
        solutions[job_id] = data
        path = config.cache / f"{job_id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "recipe": jobs[job_id],
                    "solution": data,
                    "solution_sha256": _hash(data),
                    "execution_provenance": {
                        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                    },
                }
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
        r = jobs[job_id]
        progress(
            f"{len(solutions)}/{len(jobs)} · {Path(r['instance']).stem} · "
            f"seed {r['seed']} · {r['algorithm']} · fitness {data['fitness']:.2f} · "
            f"{data['tempo_exec_s']:.2f}s"
        )

    if workers == 1:
        for job_id, recipe in pending.items():
            save(job_id, _execute(recipe))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_execute, recipe): job_id for job_id, recipe in pending.items()
            }
            for future in as_completed(futures):
                save(futures[future], future.result())
    metadata = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "study": config.model_dump(mode="json"),
        "jobs": jobs,
        "workers": workers,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "observations": len(design),
        "unique_runs": len(jobs),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_provenance": {
            job_id: json.loads((config.cache / f"{job_id}.json").read_text("utf-8")).get(
                "execution_provenance", {}
            )
            for job_id in jobs
        },
        "timing": "tempo do otimizador sob concorrência; não é benchmark isolado",
    }
    return {key: solutions[key] for key in sorted(solutions)}, design, metadata


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--render-only", action="store_true", help="Recria análise dos JSONs salvos."
    )
    args = parser.parse_args(argv)
    try:
        config = load_study_config(args.config)
        from .study_report import write_study_report

        if args.render_only:
            solutions, design, metadata = [
                json.loads((config.out / name).read_text("utf-8"))
                for name in ("solutions.json", "design.json", "metadata.json")
            ]
        else:
            solutions, design, metadata = run_study(config, workers=args.workers)
        write_study_report(config, solutions, design, metadata)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.error(str(error))
    print(f"Resultados: {config.out}; figuras: {config.figures}")


if __name__ == "__main__":
    main()
