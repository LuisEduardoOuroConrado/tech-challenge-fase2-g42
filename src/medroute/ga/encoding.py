"""Representação genética: permutação dos IDs de entrega (giant tour)."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable

from medroute.domain.models import Instance

Chromosome = list[str]
ScoreFunction = Callable[[Chromosome], float]


def create_individual(inst: Instance, rng: random.Random) -> Chromosome:
    chromosome = [delivery.id for delivery in inst.deliveries]
    rng.shuffle(chromosome)
    return chromosome


def create_population(inst: Instance, size: int, rng: random.Random) -> list[Chromosome]:
    if size < 2:
        raise ValueError("a população deve ter pelo menos 2 indivíduos")
    return [create_individual(inst, rng) for _ in range(size)]


def validate_chromosome(chromosome: Chromosome, inst: Instance) -> None:
    """Garante que o cromossomo contém cada entrega da instância exatamente uma vez."""
    expected = {delivery.id for delivery in inst.deliveries}
    counts = Counter(chromosome)
    duplicated = sorted(gene for gene, count in counts.items() if count > 1)
    missing = sorted(expected - counts.keys())
    extra = sorted(counts.keys() - expected)
    if duplicated or missing or extra:
        raise ValueError(
            f"cromossomo inválido: duplicados={duplicated}, ausentes={missing}, extras={extra}"
        )
