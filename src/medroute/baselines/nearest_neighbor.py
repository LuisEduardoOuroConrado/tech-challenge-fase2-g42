"""Nearest Neighbor: sempre visita a entrega mais próxima ainda não atendida."""

from time import perf_counter

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Solution
from medroute.ga import fitness

from ._common import FitnessFunction, build_solution


def nearest_neighbor_order(inst: Instance, dm: DistanceMatrix) -> list[str]:
    """Produz o giant tour; empates de distância são resolvidos pelo ID da entrega."""
    remaining = {index: delivery.id for index, delivery in enumerate(inst.deliveries, 1)}
    order: list[str] = []
    current = 0
    while remaining:
        nearest = min(remaining, key=lambda index: (dm.km(current, index), remaining[index]))
        order.append(remaining.pop(nearest))
        current = nearest
    return order


def solve_nearest_neighbor(
    inst: Instance,
    dm: DistanceMatrix,
    *,
    seed: int = 42,
    fitness_fn: FitnessFunction | None = None,
) -> Solution:
    """Retorna uma Solution determinística; seed é registrada para comparação."""
    started_at = perf_counter()
    return build_solution(
        nearest_neighbor_order(inst, dm),
        inst,
        dm,
        algorithm="nearest_neighbor",
        seed=seed,
        started_at=started_at,
        fitness_fn=fitness.evaluate if fitness_fn is None else fitness_fn,
    )
