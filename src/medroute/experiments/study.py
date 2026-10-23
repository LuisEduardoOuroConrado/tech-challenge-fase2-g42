"""Matriz E1–E6 com execuções deduplicadas, retomada e validação dos resultados."""

from __future__ import annotations

import hashlib
import json
import platform
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
from medroute.data import load_instance
from medroute.ga import GAConfig
from medroute.ga.fitness import FitnessConfig

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
