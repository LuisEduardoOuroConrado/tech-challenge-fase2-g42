"""Baseline aleatório: uma permutação por seed, sem busca pelo melhor sorteio."""

from random import Random
from time import perf_counter

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Solution
from medroute.ga import fitness
from medroute.ga.encoding import create_individual

from ._common import FitnessFunction, build_solution


def solve_random(
    inst: Instance,
    dm: DistanceMatrix,
    *,
    seed: int = 42,
    fitness_fn: FitnessFunction | None = None,
) -> Solution:
    """Usa um gerador local, sem modificar o estado aleatório global."""
    started_at = perf_counter()
    return build_solution(
        create_individual(inst, Random(seed)),
        inst,
        dm,
        algorithm="random",
        seed=seed,
        started_at=started_at,
        fitness_fn=fitness.evaluate if fitness_fn is None else fitness_fn,
    )
