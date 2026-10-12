"""Núcleo do algoritmo genético (Spec 02)."""

from .decoder import decode, split_decode
from .encoding import (
    Chromosome,
    ScoreFunction,
    create_individual,
    create_population,
    nearest_neighbor_chromosome,
    validate_chromosome,
)
from .engine import GAConfig, GeneticAlgorithm
from .fitness import Fitness, FitnessConfig, load_fitness_config, make_fitness
from .operators import (
    inversion_mutation,
    order_crossover,
    pmx_crossover,
    route_two_opt,
    swap_mutation,
    tournament_select,
    two_opt_local,
)

__all__ = [
    "Chromosome",
    "Fitness",
    "FitnessConfig",
    "GAConfig",
    "GeneticAlgorithm",
    "ScoreFunction",
    "create_individual",
    "create_population",
    "decode",
    "inversion_mutation",
    "load_fitness_config",
    "make_fitness",
    "nearest_neighbor_chromosome",
    "order_crossover",
    "pmx_crossover",
    "route_two_opt",
    "split_decode",
    "swap_mutation",
    "tournament_select",
    "two_opt_local",
    "validate_chromosome",
]
