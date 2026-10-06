"""Decoder giant tour -> rotas por veículo (split guloso, determinístico).

O giant tour é percorrido em ordem. A rota atual cresce enquanto existir algum veículo livre
capaz de levá-la (peso, volume, autonomia e refrigeração). Quando a próxima entrega não cabe,
a rota é fechada com o veículo livre mais barato que a comporta e uma nova rota é aberta.
Sem veículos sobrando, as entregas restantes ficam na última rota e a violação é registrada:
nenhuma entrega é descartada.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Delivery, Instance, Route, Vehicle

from .encoding import Chromosome, validate_chromosome


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
