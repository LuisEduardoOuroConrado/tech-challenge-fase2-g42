"""Loader + validação: frota (YAML) e instâncias (JSON no formato do domain/models.py)."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from medroute.domain.models import Instance, Priority, Vehicle

from .fleet import FleetConfig


class DataError(ValueError):
    pass


def load_fleet(path: str | Path = "configs/frota.yaml") -> FleetConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    try:
        veiculos, sem_volumoso = [], set()
        for tipo, cfg in raw["tipos"].items():
            cfg = dict(cfg)
            qtd = int(cfg.pop("quantidade"))
            if qtd <= 0:
                raise DataError(f"{tipo}.quantidade deve ser > 0")
            if not cfg.pop("aceita_volumoso", True):
                sem_volumoso.add(tipo)
            cfg["custo_fixo"] = cfg.pop("custo_fixo_dia")
            for i in range(1, qtd + 1):
                veiculos.append(Vehicle(id=f"{tipo}-{i:02d}", tipo=tipo, **cfg))
        g = raw.get("global", {})
        return FleetConfig(
            vehicles=tuple(veiculos),
            fator_tortuosidade=float(g.get("fator_tortuosidade", 1.30)),
            jornada_max_min=float(g.get("jornada_max_min", 480)),
            inicio_jornada=str(g.get("inicio_jornada", "07:00")),
            volumoso_limiar_l=float(g.get("volumoso_limiar_l", 60)),
            servico_min_padrao=float(g.get("servico_min_padrao", 10)),
            tipos_sem_volumoso=frozenset(sem_volumoso),
            transito=tuple(g.get("transito", [])),
            penalidade_prioridade=dict(g.get("penalidade_prioridade_rs_min", {})),
        )
    except DataError:
        raise
    except (KeyError, TypeError, ValidationError) as e:
        raise DataError(f"frota.yaml inválido: {e}") from e


def save_instance(inst: Instance, path: str | Path) -> None:
    Path(path).write_text(inst.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_instance(path: str | Path, fleet: FleetConfig | None = None) -> Instance:
    try:
        inst = Instance.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except ValidationError as e:
        raise DataError(f"instância inválida: {e}") from e
    validate_instance(inst, fleet)
    return inst


def validate_instance(inst: Instance, fleet: FleetConfig | None = None) -> None:
    """Regras além das do modelo (que já checa ids únicos e deadline só p/ crítica)."""
    erros: list[str] = []
    for d in inst.deliveries:
        if d.peso_kg <= 0 or d.volume_l <= 0:
            erros.append(f"{d.id}: peso/volume devem ser > 0")
        if d.prioridade is Priority.CRITICA and d.deadline_min is None:
            erros.append(f"{d.id}: crítica sem deadline_min")
        if fleet and not any(fleet.aceita(v, d) for v in fleet.vehicles):
            erros.append(f"{d.id}: nenhum veículo da frota atende esta entrega")
    if fleet:
        cap = sum(v.capacidade_kg for v in fleet.vehicles)
        if sum(d.peso_kg for d in inst.deliveries) > cap:
            erros.append("peso total excede a capacidade somada da frota")
    if erros:
        raise DataError("; ".join(erros))
