"""Montagem de soluções usando os mesmos decoder e fitness do GA."""

from collections.abc import Callable
from time import perf_counter

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Route, Solution
from medroute.ga import fitness
from medroute.ga.decoder import decode, split_decode

FitnessFunction = Callable[[list[Route]], float]


def decode_routes(
    chromosome: list[str], inst: Instance, dm: DistanceMatrix, fitness_fn: FitnessFunction
) -> list[Route]:
    """Mesma escolha de decoder do GA; Fitness leva também frota e restrições P1."""
    if isinstance(fitness_fn, fitness.Fitness):
        return split_decode(
            chromosome, inst, dm, fitness_fn.cfg, fitness_fn.servico_min, fitness_fn.fleet
        )
    return decode(chromosome, inst, dm)


def build_solution(
    chromosome: list[str],
    inst: Instance,
    dm: DistanceMatrix,
    *,
    algorithm: str,
    seed: int,
    started_at: float,
    fitness_fn: FitnessFunction,
    initial_fitness: float | None = None,
) -> Solution:
    routes = decode_routes(chromosome, inst, dm, fitness_fn)
    score = fitness_fn(routes)
    history = [score] if initial_fitness is None else [initial_fitness, score]
    return Solution(
        instance_nome=inst.nome,
        algoritmo=algorithm,
        routes=routes,
        fitness=score,
        custo_operacional=sum(route.custo for route in routes),
        distancia_total_km=sum(route.distancia_km for route in routes),
        penalidades=(
            fitness_fn.penalties(routes)
            if isinstance(fitness_fn, fitness.Fitness)
            else fitness.penalties(routes)
        ),
        historico_fitness=history,
        tempo_exec_s=perf_counter() - started_at,
        seed=seed,
    )
