"""Abordagens de referência com a mesma saída Solution do algoritmo genético."""

from .nearest_neighbor import solve_nearest_neighbor
from .random import solve_random
from .two_opt import solve_nearest_neighbor_two_opt

__all__ = ["solve_nearest_neighbor", "solve_nearest_neighbor_two_opt", "solve_random"]
