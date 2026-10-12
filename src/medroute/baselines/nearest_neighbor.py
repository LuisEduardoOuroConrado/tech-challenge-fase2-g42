"""Nearest Neighbor: sempre visita a entrega mais próxima ainda não atendida."""

from time import perf_counter

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Solution
from medroute.ga import fitness
from medroute.ga.encoding import nearest_neighbor_chromosome

from ._common import FitnessFunction, build_solution


def nearest_neighbor_order(inst: Instance, dm: DistanceMatrix) -> list[str]:
    """Produz o giant tour; empates de distância são resolvidos pelo ID da entrega."""
    return nearest_neighbor_chromosome(inst, dm)


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
