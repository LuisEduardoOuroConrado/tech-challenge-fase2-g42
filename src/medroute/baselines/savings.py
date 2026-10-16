"""Clarke-Wright paralelo: economias em km geram um giant tour com split compartilhado.

As fusões preservam capacidade, autonomia e compatibilidade para pelo menos um veículo.
O decoder final atribui a frota finita e, com Fitness, escolhe os cortes pelo custo em R$.
"""

from itertools import combinations, pairwise
from time import perf_counter

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Solution
from medroute.ga import fitness

from ._common import FitnessFunction, build_solution


def savings_chains(
    inst: Instance, dm: DistanceMatrix, fitness_fn: FitnessFunction = fitness.evaluate
) -> list[list[str]]:
    """Funde só extremidades de cadeias distintas; desempata economias pelos IDs."""
    index_of = {delivery.id: i for i, delivery in enumerate(inst.deliveries, start=1)}
    delivery_of = {delivery.id: delivery for delivery in inst.deliveries}
    identifiers = sorted(index_of)
    chains = {identifier: [identifier] for identifier in identifiers}
    owner = {identifier: identifier for identifier in identifiers}
    fleet = fitness_fn.fleet if isinstance(fitness_fn, fitness.Fitness) else None

    def feasible(chain: list[str]) -> bool:
        deliveries = [delivery_of[identifier] for identifier in chain]
        kg = sum(delivery.peso_kg for delivery in deliveries)
        litres = sum(delivery.volume_l for delivery in deliveries)
        legs = [0, *(index_of[identifier] for identifier in chain), 0]
        km = sum(dm.km(a, b) for a, b in pairwise(legs))
        return any(
            kg <= vehicle.capacidade_kg
            and litres <= vehicle.capacidade_l
            and km <= vehicle.autonomia_km
            and all(
                fleet.compativel(vehicle, delivery)
                if fleet is not None
                else vehicle.aceita_refrigerado or not delivery.refrigerado
                for delivery in deliveries
            )
            for vehicle in inst.fleet
        )

    savings = sorted(
        (
            (
                -(dm.km(0, index_of[a]) + dm.km(0, index_of[b]) - dm.km(index_of[a], index_of[b])),
                a,
                b,
            )
            for a, b in combinations(identifiers, 2)
        )
    )
    for negative_saving, a, b in savings:
        if negative_saving >= 0:
            break
        left_key, right_key = owner[a], owner[b]
        if left_key == right_key:
            continue
        left, right = chains[left_key], chains[right_key]
        if a not in (left[0], left[-1]) or b not in (right[0], right[-1]):
            continue
        joined = (left if left[-1] == a else left[::-1]) + (right if right[0] == b else right[::-1])
        if not feasible(joined):
            continue
        chains[left_key] = joined
        del chains[right_key]
        for identifier in joined:
            owner[identifier] = left_key

    return [chains[key] for key in sorted(chains)]


def savings_order(
    inst: Instance, dm: DistanceMatrix, fitness_fn: FitnessFunction = fitness.evaluate
) -> list[str]:
    """Concatena as cadeias para atribuição da frota pelo decoder compartilhado."""
    return [identifier for chain in savings_chains(inst, dm, fitness_fn) for identifier in chain]


def solve_savings(
    inst: Instance,
    dm: DistanceMatrix,
    *,
    seed: int = 42,
    fitness_fn: FitnessFunction | None = None,
) -> Solution:
    """Baseline determinístico; sem frota viável, preserva entregas e registra violações."""
    started_at = perf_counter()
    evaluate = fitness.evaluate if fitness_fn is None else fitness_fn
    return build_solution(
        savings_order(inst, dm, evaluate),
        inst,
        dm,
        algorithm="savings",
        seed=seed,
        started_at=started_at,
        fitness_fn=evaluate,
    )
