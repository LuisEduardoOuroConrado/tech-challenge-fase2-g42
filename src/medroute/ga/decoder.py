"""Decoders giant tour -> rotas por veículo (determinísticos).

`decode` (split guloso): o giant tour é percorrido em ordem. A rota atual cresce enquanto
existir algum veículo livre capaz de levá-la (peso, volume, autonomia e refrigeração). Quando a
próxima entrega não cabe, a rota é fechada com o veículo livre mais barato que a comporta e uma
nova rota é aberta. Sem veículos sobrando, as entregas restantes ficam na última rota e a
violação é registrada: nenhuma entrega é descartada.

`split_decode` (split ótimo, Prins 2004): escolhe os cortes do giant tour e o veículo de cada
rota por programação dinâmica, minimizando custo operacional + custo de prioridade (Spec 03).
Só usa rotas sem violação hard; se a frota não comporta nenhuma divisão viável, cai no guloso,
que registra a violação.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from typing import TYPE_CHECKING

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Delivery, Instance, Route, Vehicle

from .encoding import Chromosome, validate_chromosome

if TYPE_CHECKING:
    from .fitness import FitnessConfig


class _Segment:
    """Rota parcial com métricas incrementais (índices da DistanceMatrix, sem o depósito)."""

    def __init__(self, dm: DistanceMatrix) -> None:
        self.dm = dm
        self.stops: list[int] = []
        self.deliveries: list[Delivery] = []
        self.open_km = 0.0
        self.peso_kg = 0.0
        self.volume_l = 0.0
        self.refrigerado = 0

    def total_km(self) -> float:
        return self.open_km + (self.dm.km(self.stops[-1], 0) if self.stops else 0.0)

    def km_with(self, index: int) -> float:
        last = self.stops[-1] if self.stops else 0
        return self.open_km + self.dm.km(last, index) + self.dm.km(index, 0)

    def add(self, index: int, delivery: Delivery) -> None:
        last = self.stops[-1] if self.stops else 0
        self.open_km += self.dm.km(last, index)
        self.stops.append(index)
        self.deliveries.append(delivery)
        self.peso_kg += delivery.peso_kg
        self.volume_l += delivery.volume_l
        self.refrigerado += delivery.refrigerado


def _violations(vehicle: Vehicle, peso_kg: float, volume_l: float, km: float, refrigerado: int):
    return {
        "capacidade": max(0.0, peso_kg / vehicle.capacidade_kg - 1)
        + max(0.0, volume_l / vehicle.capacidade_l - 1),
        "autonomia": max(0.0, km - vehicle.autonomia_km),
        "compatibilidade": 0.0 if vehicle.aceita_refrigerado else float(refrigerado),
    }


def _fits(vehicle: Vehicle, peso_kg: float, volume_l: float, km: float, refrigerado: int) -> bool:
    return not any(_violations(vehicle, peso_kg, volume_l, km, refrigerado).values())


def _fits_with(vehicle: Vehicle, segment: _Segment, index: int, delivery: Delivery) -> bool:
    return _fits(
        vehicle,
        segment.peso_kg + delivery.peso_kg,
        segment.volume_l + delivery.volume_l,
        segment.km_with(index),
        segment.refrigerado + delivery.refrigerado,
    )


def _route_cost(vehicle: Vehicle, km: float) -> float:
    return vehicle.custo_fixo + vehicle.custo_km * km


def _choose_vehicle(segment: _Segment, free: Sequence[Vehicle]) -> Vehicle:
    """Veículo viável mais barato; sem viável, o de menor violação. Empate: ordem da frota."""
    km = segment.total_km()

    def key(vehicle: Vehicle) -> tuple[float, float]:
        violations = _violations(
            vehicle, segment.peso_kg, segment.volume_l, km, segment.refrigerado
        )
        return sum(violations.values()), _route_cost(vehicle, km)

    return min(free, key=key)


def _build_route(segment: _Segment, vehicle: Vehicle, dm: DistanceMatrix) -> Route:
    km = segment.total_km()
    legs = [0, *segment.stops, 0]
    duracao = sum(dm.time(a, b, vehicle.velocidade_kmh) for a, b in pairwise(legs))
    return Route(
        vehicle_id=vehicle.id,
        sequence=[delivery.id for delivery in segment.deliveries],
        distancia_km=km,
        duracao_min=duracao,
        carga_kg=segment.peso_kg,
        carga_l=segment.volume_l,
        custo=_route_cost(vehicle, km),
        violacoes=_violations(vehicle, segment.peso_kg, segment.volume_l, km, segment.refrigerado),
    )


def decode(chromosome: Chromosome, inst: Instance, dm: DistanceMatrix) -> list[Route]:
    validate_chromosome(chromosome, inst)
    index_of = {delivery.id: i for i, delivery in enumerate(inst.deliveries, start=1)}
    delivery_of = {delivery.id: delivery for delivery in inst.deliveries}

    free = list(inst.fleet)
    routes: list[Route] = []
    segment = _Segment(dm)
    for delivery_id in chromosome:
        index, delivery = index_of[delivery_id], delivery_of[delivery_id]
        can_extend = not segment.stops or any(
            _fits_with(vehicle, segment, index, delivery) for vehicle in free
        )
        if not can_extend and len(free) > 1:
            vehicle = _choose_vehicle(segment, free)
            free.remove(vehicle)
            routes.append(_build_route(segment, vehicle, dm))
            segment = _Segment(dm)
        segment.add(index, delivery)

    routes.append(_build_route(segment, _choose_vehicle(segment, free), dm))
    return routes


def _vehicle_groups(fleet: Sequence[Vehicle]) -> list[list[Vehicle]]:
    """Agrupa veículos idênticos (exceto o id), na ordem da frota."""
    groups: dict[tuple, list[Vehicle]] = {}
    for vehicle in fleet:
        groups.setdefault(tuple(vehicle.model_dump(exclude={"id"}).values()), []).append(vehicle)
    return list(groups.values())


def _feasible_segments(
    vehicle: Vehicle,
    stops: list[int],
    deliveries: list[Delivery],
    weights: list[float],
    km: list[list[float]],
    servico_min: float,
) -> list[list[tuple[int, float]]]:
    """Para cada início i, as rotas viáveis i..j-1 como (j, custo operacional + prioridade).

    Carga, refrigerados e km com retorno só crescem ao estender a rota (desigualdade
    triangular), então a primeira violação encerra a extensão.
    """
    n = len(stops)
    segments: list[list[tuple[int, float]]] = []
    for start in range(n):
        out: list[tuple[int, float]] = []
        open_km = relogio = prioridade = peso_kg = volume_l = 0.0
        last = 0
        for j in range(start, n):
            delivery, stop = deliveries[j], stops[j]
            peso_kg += delivery.peso_kg
            volume_l += delivery.volume_l
            if (
                (delivery.refrigerado and not vehicle.aceita_refrigerado)
                or peso_kg > vehicle.capacidade_kg
                or volume_l > vehicle.capacidade_l
            ):
                break
            leg = km[last][stop]
            open_km += leg
            relogio += leg / vehicle.velocidade_kmh * 60.0
            prioridade += weights[j] * relogio
            relogio += servico_min
            last = stop
            total_km = open_km + km[stop][0]
            if total_km > vehicle.autonomia_km:
                break
            out.append((j + 1, _route_cost(vehicle, total_km) + prioridade))
        segments.append(out)
    return segments


def split_decode(
    chromosome: Chromosome,
    inst: Instance,
    dm: DistanceMatrix,
    cfg: FitnessConfig,
    servico_min: float,
) -> list[Route]:
    validate_chromosome(chromosome, inst)
    index_of = {delivery.id: i for i, delivery in enumerate(inst.deliveries, start=1)}
    delivery_of = {delivery.id: delivery for delivery in inst.deliveries}
    stops = [index_of[delivery_id] for delivery_id in chromosome]
    deliveries = [delivery_of[delivery_id] for delivery_id in chromosome]
    weights = [cfg.prioridade_rs_min[delivery.prioridade] for delivery in deliveries]
    km = dm.matrix().tolist()
    n = len(stops)

    groups = _vehicle_groups(inst.fleet)
    limits = tuple(len(group) for group in groups)
    segments = [
        _feasible_segments(group[0], stops, deliveries, weights, km, servico_min)
        for group in groups
    ]

    # best[j][usados] = menor custo cobrindo as j primeiras entregas com `usados` veículos por
    # grupo; back guarda (início, estado anterior, grupo) para reconstruir as rotas.
    start_state = (0,) * len(groups)
    best: list[dict[tuple[int, ...], float]] = [{} for _ in range(n + 1)]
    back: list[dict[tuple[int, ...], tuple[int, tuple[int, ...], int]]] = [{} for _ in range(n + 1)]
    best[0][start_state] = 0.0
    for i in range(n):
        for state, base in best[i].items():
            for g, limit in enumerate(limits):
                if state[g] >= limit:
                    continue
                next_state = (*state[:g], state[g] + 1, *state[g + 1 :])
                for j, cost in segments[g][i]:
                    total = base + cost
                    current = best[j].get(next_state)
                    if current is None or total < current:
                        best[j][next_state] = total
                        back[j][next_state] = (i, state, g)

    if not best[n]:
        return decode(chromosome, inst, dm)

    state = min(best[n], key=lambda s: (best[n][s], s))
    cuts: list[tuple[int, int, int]] = []
    j = n
    while j > 0:
        i, previous, g = back[j][state]
        cuts.append((i, j, g))
        j, state = i, previous
    cuts.reverse()

    free = [list(group) for group in groups]
    routes = []
    for i, j, g in cuts:
        segment = _Segment(dm)
        for k in range(i, j):
            segment.add(stops[k], deliveries[k])
        routes.append(_build_route(segment, free[g].pop(0), dm))
    return routes
