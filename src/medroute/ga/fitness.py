"""Fitness em R$ (Spec 03): custo operacional + custo de prioridade + penalidades.

`make_fitness` monta a função definitiva a partir de `configs/fitness.yaml`. `evaluate` e
`penalties(routes)` sem configuração são a versão provisória (sem prioridade), mantida como
padrão do `GeneticAlgorithm` para quem ainda não passa um `FitnessConfig`.

`cronograma_rota` e `custo_prioridade` são PROVISÓRIOS: pertencem a `constraints/` (Beatriz,
14/10) e estão aqui com a assinatura da Spec 03, seção 3. Quando `constraints/` entrar, troca-se
a definição local pelo import, sem mudar quem chama.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from medroute.data.distance import DistanceMatrix
from medroute.data.fleet import FleetConfig
from medroute.domain.models import Delivery, Instance, Priority, Route, Vehicle

FITNESS_PATH = Path("configs/fitness.yaml")
PENALTY_KEYS = ("capacidade", "autonomia", "compatibilidade", "deadline", "jornada")

# Versão provisória: só os unitários das penalidades hard, sem fixo e sem prioridade.
PENALTY_WEIGHTS: dict[str, float] = {
    "capacidade": 2000.0,  # R$ por 100 % de excesso
    "autonomia": 20.0,  # R$ por km acima da autonomia
    "compatibilidade": 1000.0,  # R$ por entrega incompatível
}

NonNegative = Annotated[float, Field(ge=0)]


class PenaltyWeight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixo: NonNegative
    unitario: NonNegative


class FitnessConfig(BaseModel):
    """Espelha `configs/fitness.yaml`."""

    model_config = ConfigDict(extra="forbid")

    prioridade_rs_min: dict[Priority, NonNegative]
    penalidades: dict[str, PenaltyWeight]

    @model_validator(mode="after")
    def chaves_obrigatorias(self) -> Self:
        faltando = [p.value for p in Priority if p not in self.prioridade_rs_min]
        if faltando:
            raise ValueError(f"prioridade_rs_min sem: {', '.join(faltando)}")
        faltando = [key for key in PENALTY_KEYS if key not in self.penalidades]
        if faltando:
            raise ValueError(f"penalidades sem: {', '.join(faltando)}")
        return self

    def penalty(self, key: str, amount: float) -> float:
        """R$ de uma violação em uma rota: fixo (se > 0) + unitário × quantidade."""
        if amount <= 0:
            return 0.0
        weight = self.penalidades[key]
        return weight.fixo + weight.unitario * amount


def load_fitness_config(path: str | Path = FITNESS_PATH) -> FitnessConfig:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return FitnessConfig.model_validate(data)
    except (ValidationError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: configuração de fitness inválida: {error}") from error


def penalties(routes: list[Route], cfg: FitnessConfig | None = None) -> dict[str, float]:
    """R$ por tipo de violação, somado nas rotas (vai para `Solution.penalidades`)."""
    totals: dict[str, float] = {}
    for route in routes:
        for key, amount in route.violacoes.items():
            if cfg is None:
                value = amount * PENALTY_WEIGHTS.get(key, 0.0)
            else:
                value = cfg.penalty(key, amount)
            totals[key] = totals.get(key, 0.0) + value
    return totals


def evaluate(routes: list[Route]) -> float:
    """Fitness provisório: custo operacional + penalidades sem fixo, sem prioridade."""
    return sum(route.custo for route in routes) + sum(penalties(routes).values())


# --- Provisório até constraints/ (Spec 03, seção 3) ------------------------------------------


def cronograma_rota(
    dm: DistanceMatrix,
    veiculo: Vehicle,
    rota: Sequence[str],
    instance: Instance,
    fleet: FleetConfig,
    saida_min: float | None = None,
) -> dict[str, float]:
    """Minuto de chegada a cada entrega desde a saída do depósito (P0: sem trânsito)."""
    if saida_min is not None:
        raise NotImplementedError("fator de trânsito é P1 (constraints/, 21/10)")
    index_of = {d.id: i for i, d in enumerate(instance.deliveries, start=1)}
    chegadas: dict[str, float] = {}
    relogio, anterior = 0.0, 0
    for delivery_id in rota:
        atual = index_of[delivery_id]
        relogio += dm.time(anterior, atual, veiculo.velocidade_kmh)
        chegadas[delivery_id] = relogio
        relogio += fleet.servico_min_padrao
        anterior = atual
    return chegadas


def custo_prioridade(
    chegadas_min: dict[str, float],
    entregas: Sequence[Delivery],
    pesos: dict[Priority, float],
) -> float:
    """Σ peso da prioridade (R$/min) × minuto de chegada."""
    return sum(pesos[d.prioridade] * chegadas_min[d.id] for d in entregas if d.id in chegadas_min)


# ----------------------------------------------------------------------------------------------


class Fitness:
    """Função de fitness definitiva; é chamável como `fitness_fn` do GA (Spec 02)."""

    def __init__(
        self, inst: Instance, dm: DistanceMatrix, fleet: FleetConfig, cfg: FitnessConfig
    ) -> None:
        self.inst = inst
        self.dm = dm
        self.fleet = fleet
        self.cfg = cfg
        self._vehicles = {vehicle.id: vehicle for vehicle in inst.fleet}
        self._deliveries = {delivery.id: delivery for delivery in inst.deliveries}

    @property
    def servico_min(self) -> float:
        return self.fleet.servico_min_padrao

    def priority_cost(self, routes: list[Route]) -> float:
        total = 0.0
        for route in routes:
            chegadas = cronograma_rota(
                self.dm, self._vehicles[route.vehicle_id], route.sequence, self.inst, self.fleet
            )
            entregas = [self._deliveries[delivery_id] for delivery_id in route.sequence]
            total += custo_prioridade(chegadas, entregas, self.cfg.prioridade_rs_min)
        return total

    def penalties(self, routes: list[Route]) -> dict[str, float]:
        return penalties(routes, self.cfg)

    def __call__(self, routes: list[Route]) -> float:
        return (
            sum(route.custo for route in routes)
            + self.priority_cost(routes)
            + sum(self.penalties(routes).values())
        )


def make_fitness(
    inst: Instance, dm: DistanceMatrix, fleet: FleetConfig, cfg: FitnessConfig
) -> Fitness:
    return Fitness(inst, dm, fleet, cfg)
