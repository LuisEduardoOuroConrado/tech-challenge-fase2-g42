"""Cronograma de uma rota e custo de prioridade (Spec 03, seções 2 e 3).

Convenções:
- `rota` = ids das entregas na ordem de visita, sem o depósito (como em `Route.sequence`).
- As chegadas contam minutos desde a saída do depósito (a mesma referência de `deadline_min`).
- Cada parada gasta `FleetConfig.servico_min_padrao` minutos *depois* da chegada.
- `saida_min=None` (P0): tempo = km / velocidade. Com `saida_min` (minuto do dia da partida,
  ex. 420 = 07:00; P1) cada trecho é multiplicado pelo fator de trânsito do período em que ele
  sai (`DistanceMatrix.time`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from medroute.data.distance import DistanceMatrix
from medroute.data.fleet import FleetConfig
from medroute.domain.models import Delivery, Instance, Priority, Vehicle


def _percorrer(
    dm: DistanceMatrix,
    veiculo: Vehicle,
    rota: Sequence[str],
    instance: Instance,
    fleet: FleetConfig,
    saida_min: float | None,
) -> tuple[dict[str, float], float]:
    """(chegadas por entrega, duração total até voltar ao depósito)."""
    if not rota:
        return {}, 0.0
    index_of = {d.id: i for i, d in enumerate(instance.deliveries, start=1)}
    chegadas: dict[str, float] = {}
    relogio, anterior = 0.0, 0
    for delivery_id in rota:
        atual = index_of[delivery_id]
        partida = None if saida_min is None else saida_min + relogio
        relogio += dm.time(anterior, atual, veiculo.velocidade_kmh, partida)
        chegadas[delivery_id] = relogio
        relogio += fleet.servico_min_padrao
        anterior = atual
    partida = None if saida_min is None else saida_min + relogio
    relogio += dm.time(anterior, 0, veiculo.velocidade_kmh, partida)
    return chegadas, relogio


def cronograma_rota(
    dm: DistanceMatrix,
    veiculo: Vehicle,
    rota: Sequence[str],
    instance: Instance,
    fleet: FleetConfig,
    saida_min: float | None = None,
) -> dict[str, float]:
    """Minuto de chegada a cada entrega, antes do atendimento."""
    return _percorrer(dm, veiculo, rota, instance, fleet, saida_min)[0]


def duracao_rota(
    dm: DistanceMatrix,
    veiculo: Vehicle,
    rota: Sequence[str],
    instance: Instance,
    fleet: FleetConfig,
    saida_min: float | None = None,
) -> float:
    """Minutos da saída do depósito até a volta (viagem + paradas); rota vazia = 0.

    É o valor que `violacao_jornada` compara com `jornada_max_min`."""
    return _percorrer(dm, veiculo, rota, instance, fleet, saida_min)[1]


def custo_prioridade(
    chegadas_min: Mapping[str, float],
    entregas: Sequence[Delivery],
    pesos: Mapping[Priority, float],
) -> float:
    """R$: soma de (peso da prioridade em R$/min) x (minuto de chegada).

    Faz as críticas virem antes. Entregas sem chegada em `chegadas_min` não contam."""
    return sum(pesos[d.prioridade] * chegadas_min[d.id] for d in entregas if d.id in chegadas_min)
