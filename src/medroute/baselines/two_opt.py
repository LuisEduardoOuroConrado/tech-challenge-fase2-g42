"""NN seguido por busca local 2-opt no giant tour, usando o fitness compartilhado."""

from time import perf_counter

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Solution
from medroute.ga import fitness
from medroute.ga.decoder import decode
from medroute.ga.operators import two_opt_local

from ._common import FitnessFunction, build_solution
from .nearest_neighbor import nearest_neighbor_order


def solve_nearest_neighbor_two_opt(
    inst: Instance,
    dm: DistanceMatrix,
    *,
    seed: int = 42,
    max_passes: int = 100,
    fitness_fn: FitnessFunction | None = None,
) -> Solution:
    """Para sem melhoria ou após max_passes; só aceita redução estrita de fitness."""
    if max_passes < 1:
        raise ValueError("max_passes deve ser pelo menos 1")
    started_at = perf_counter()
    evaluate = fitness.evaluate if fitness_fn is None else fitness_fn

    def score(chromosome: list[str]) -> float:
        return evaluate(decode(chromosome, inst, dm))

    initial = nearest_neighbor_order(inst, dm)
    initial_fitness = score(initial)
    improved = two_opt_local(initial, score, max_passes=max_passes)
    return build_solution(
        improved,
        inst,
        dm,
        algorithm="nearest_neighbor_two_opt",
        seed=seed,
        started_at=started_at,
        fitness_fn=evaluate,
        initial_fitness=initial_fitness,
    )
