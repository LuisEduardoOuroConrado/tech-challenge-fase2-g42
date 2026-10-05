"""Operadores genéticos para permutações: seleção, crossover, mutação e 2-opt.

Nenhum operador altera os cromossomos recebidos; todos devolvem cópias.
"""

from __future__ import annotations

import random

from .encoding import Chromosome, ScoreFunction


def _cut_points(size: int, rng: random.Random) -> tuple[int, int]:
    """Dois índices distintos, em ordem crescente, que delimitam um segmento inclusivo."""
    i, j = rng.sample(range(size), 2)
    return min(i, j), max(i, j)


def tournament_select(
    population: list[Chromosome],
    fitnesses: list[float],
    tournament_size: int,
    rng: random.Random,
) -> Chromosome:
    if len(population) != len(fitnesses):
        raise ValueError("population e fitnesses devem ter o mesmo tamanho")
    if not 2 <= tournament_size <= len(population):
        raise ValueError("tournament_size deve estar entre 2 e o tamanho da população")
    contenders = rng.sample(range(len(population)), tournament_size)
    winner = min(contenders, key=lambda index: fitnesses[index])
    return list(population[winner])


def _ox_child(donor: Chromosome, filler: Chromosome, start: int, end: int) -> Chromosome:
    size = len(donor)
    child: list[str | None] = [None] * size
    child[start : end + 1] = donor[start : end + 1]
    kept = set(donor[start : end + 1])
    position = (end + 1) % size
    for offset in range(size):
        gene = filler[(end + 1 + offset) % size]
        if gene in kept:
            continue
        child[position] = gene
        position = (position + 1) % size
    return [gene for gene in child if gene is not None]


def order_crossover(
    parent_a: Chromosome,
    parent_b: Chromosome,
    rng: random.Random,
) -> tuple[Chromosome, Chromosome]:
    if len(parent_a) < 2:
        return list(parent_a), list(parent_b)
    start, end = _cut_points(len(parent_a), rng)
    return (
        _ox_child(parent_a, parent_b, start, end),
        _ox_child(parent_b, parent_a, start, end),
    )


def _pmx_child(donor: Chromosome, filler: Chromosome, start: int, end: int) -> Chromosome:
    child = list(filler)
    child[start : end + 1] = donor[start : end + 1]
    mapping = {donor[i]: filler[i] for i in range(start, end + 1)}
    segment = set(donor[start : end + 1])
    for i in [*range(start), *range(end + 1, len(child))]:
        gene = filler[i]
        while gene in segment:
            gene = mapping[gene]
        child[i] = gene
    return child


def pmx_crossover(
    parent_a: Chromosome,
    parent_b: Chromosome,
    rng: random.Random,
) -> tuple[Chromosome, Chromosome]:
    if len(parent_a) < 2:
        return list(parent_a), list(parent_b)
    start, end = _cut_points(len(parent_a), rng)
    return (
        _pmx_child(parent_a, parent_b, start, end),
        _pmx_child(parent_b, parent_a, start, end),
    )


def swap_mutation(chromosome: Chromosome, rng: random.Random) -> Chromosome:
    mutant = list(chromosome)
    if len(mutant) < 2:
        return mutant
    i, j = _cut_points(len(mutant), rng)
    mutant[i], mutant[j] = mutant[j], mutant[i]
    return mutant


def inversion_mutation(chromosome: Chromosome, rng: random.Random) -> Chromosome:
    mutant = list(chromosome)
    if len(mutant) < 2:
        return mutant
    i, j = _cut_points(len(mutant), rng)
    mutant[i : j + 1] = reversed(mutant[i : j + 1])
    return mutant


def two_opt_local(
    chromosome: Chromosome,
    score: ScoreFunction,
    max_passes: int = 1,
) -> Chromosome:
    """Busca local 2-opt de primeira melhora; só aceita inversões que reduzem o score."""
    best = list(chromosome)
    if len(best) < 2:
        return best
    best_score = score(best)
    for _ in range(max_passes):
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                candidate_score = score(candidate)
                if candidate_score < best_score:
                    best, best_score = candidate, candidate_score
                    improved = True
        if not improved:
            break
    return best
