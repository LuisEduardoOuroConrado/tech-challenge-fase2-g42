"""Violações de restrição (Spec 03, seção 3): funções puras, sem efeito colateral nem sorteio.

Cada função devolve um número >= 0 e **0 significa "sem violação"**. As chaves de `CHAVES` são as
de `Route.violacoes` e `Solution.penalidades`. Os pesos em R$ ficam em `configs/fitness.yaml`
(aplicados por `ga/fitness.py`), não aqui.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from medroute.data.fleet import FleetConfig
from medroute.domain.models import Delivery, Vehicle

CHAVES = ("capacidade", "autonomia", "compatibilidade", "deadline", "jornada")


def violacao_capacidade(veiculo: Vehicle, entregas: Sequence[Delivery]) -> float:
    """Excesso de carga: max(0, kg/cap_kg - 1) + max(0, L/cap_L - 1) (frações somadas).

    Ex.: 30 kg numa moto de 15 kg => 1.0 (100 % de excesso)."""
    peso_kg = sum(e.peso_kg for e in entregas)
    volume_l = sum(e.volume_l for e in entregas)
    return max(0.0, peso_kg / veiculo.capacidade_kg - 1.0) + max(
        0.0, volume_l / veiculo.capacidade_l - 1.0
    )


def violacao_autonomia(veiculo: Vehicle, km: float) -> float:
    """Km acima da autonomia do veículo (depósito -> rota -> depósito)."""
    return max(0.0, km - veiculo.autonomia_km)


def violacao_compatibilidade(
    fleet: FleetConfig, veiculo: Vehicle, entregas: Sequence[Delivery]
) -> float:
    """Nº de entregas que o veículo não pode levar (refrigerado ou volumoso).

    Usa `FleetConfig.compativel`, e não `aceita`, porque `aceita` também confere peso e volume
    e o excesso de carga já é cobrado por `violacao_capacidade` (cobrança dupla)."""
    return float(sum(not fleet.compativel(veiculo, e) for e in entregas))


def violacao_deadline(chegadas_min: Mapping[str, float], entregas: Sequence[Delivery]) -> float:
    """Soma dos minutos de atraso (chegada - deadline_min) das entregas que têm deadline.

    `chegadas_min`: id da entrega -> minuto de chegada desde a saída do depósito (a mesma
    referência do `deadline_min`). Só as críticas têm deadline; chegar no minuto exato não
    atrasa."""
    return sum(
        max(0.0, chegadas_min[e.id] - e.deadline_min)
        for e in entregas
        if e.deadline_min is not None
    )


def violacao_jornada(duracao_min: float, fleet: FleetConfig) -> float:
    """Minutos acima de `jornada_max_min` (480 = 8 h), contando viagem, paradas e a volta."""
    return max(0.0, duracao_min - fleet.jornada_max_min)
