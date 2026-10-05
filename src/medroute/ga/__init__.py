"""Núcleo do algoritmo genético (Spec 02)."""

from .decoder import decode
from .encoding import (
    Chromosome,
    ScoreFunction,
    create_individual,
    create_population,
    validate_chromosome,
)
from .engine import GAConfig, GeneticAlgorithm
from .operators import (
    inversion_mutation,
    order_crossover,
    pmx_crossover,
    swap_mutation,
    tournament_select,
    two_opt_local,
)

__all__ = [
    "Chromosome",
    "GAConfig",
    "GeneticAlgorithm",
    "ScoreFunction",
    "create_individual",
    "create_population",
    "decode",
    "inversion_mutation",
    "order_crossover",
    "pmx_crossover",
    "swap_mutation",
    "tournament_select",
    "two_opt_local",
    "validate_chromosome",
]
