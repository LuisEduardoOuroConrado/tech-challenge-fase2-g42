"""Motor do GA: evolução geracional com torneio, elitismo e parada por estagnação."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Route, Solution

from . import fitness
from .decoder import decode
from .encoding import Chromosome, create_population, validate_chromosome
from .operators import (
    inversion_mutation,
    order_crossover,
    pmx_crossover,
    swap_mutation,
    tournament_select,
    two_opt_local,
)

FitnessFunction = Callable[[list[Route]], float]
Rate = Annotated[float, Field(ge=0, le=1)]

CROSSOVERS = {"ox": order_crossover, "pmx": pmx_crossover}


class GAConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    population_size: Annotated[int, Field(ge=2)]
    generations: Annotated[int, Field(ge=1)]
    crossover_rate: Rate
    mutation_rate: Rate
    elitism: Annotated[int, Field(ge=0)]
    tournament_size: Annotated[int, Field(ge=2)]
    crossover: Literal["ox", "pmx"]
    mutation: Literal["swap", "inversion", "two_opt"]
    patience: Annotated[int, Field(ge=1)] | None = None
    improvement_tolerance: Annotated[float, Field(ge=0)] = 1e-9

    @model_validator(mode="after")
    def limites_dependem_da_populacao(self) -> Self:
        if self.elitism >= self.population_size:
            raise ValueError("elitism deve ser menor que population_size")
        if self.tournament_size > self.population_size:
            raise ValueError("tournament_size não pode exceder population_size")
        return self


class GeneticAlgorithm:
    def __init__(
        self,
        inst: Instance,
        dm: DistanceMatrix,
        config: GAConfig,
        fitness_fn: FitnessFunction = fitness.evaluate,
    ) -> None:
        self.inst = inst
        self.dm = dm
        self.config = config
        self.fitness_fn = fitness_fn
        self._cache: dict[tuple[str, ...], float] = {}

    def score(self, chromosome: Chromosome) -> float:
        key = tuple(chromosome)
        if key not in self._cache:
            validate_chromosome(chromosome, self.inst)
            self._cache[key] = self.fitness_fn(decode(chromosome, self.inst, self.dm))
        return self._cache[key]

    def _mutate(self, chromosome: Chromosome, rng: random.Random) -> Chromosome:
        if self.config.mutation == "swap":
            return swap_mutation(chromosome, rng)
        if self.config.mutation == "inversion":
            return inversion_mutation(chromosome, rng)
        return two_opt_local(chromosome, self.score)

    def _next_generation(
        self,
        population: list[Chromosome],
        fitnesses: list[float],
        rng: random.Random,
    ) -> list[Chromosome]:
        cfg = self.config
        ranked = sorted(range(len(population)), key=lambda index: fitnesses[index])
        offspring = [list(population[index]) for index in ranked[: cfg.elitism]]
        crossover = CROSSOVERS[cfg.crossover]
        while len(offspring) < cfg.population_size:
            parent_a = tournament_select(population, fitnesses, cfg.tournament_size, rng)
            parent_b = tournament_select(population, fitnesses, cfg.tournament_size, rng)
            if rng.random() < cfg.crossover_rate:
                children = crossover(parent_a, parent_b, rng)
            else:
                children = (parent_a, parent_b)
            for child in children:
                if rng.random() < cfg.mutation_rate:
                    child = self._mutate(child, rng)
                if len(offspring) < cfg.population_size:
                    offspring.append(child)
        return offspring

    def run(self, seed: int) -> Solution:
        start = time.perf_counter()
        rng = random.Random(seed)
        cfg = self.config

        population = create_population(self.inst, cfg.population_size, rng)
        history: list[float] = []
        best: Chromosome = population[0]
        best_fitness = float("inf")
        stagnant = 0

        for generation in range(cfg.generations):
            fitnesses = [self.score(chromosome) for chromosome in population]
            generation_best = min(range(len(population)), key=lambda index: fitnesses[index])
            history.append(fitnesses[generation_best])

            if fitnesses[generation_best] < best_fitness - cfg.improvement_tolerance:
                stagnant = 0
            else:
                stagnant += 1
            if fitnesses[generation_best] < best_fitness:
                best, best_fitness = list(population[generation_best]), fitnesses[generation_best]

            if cfg.patience is not None and stagnant >= cfg.patience:
                break
            if generation < cfg.generations - 1:
                population = self._next_generation(population, fitnesses, rng)

        routes = decode(best, self.inst, self.dm)
        custo_operacional = sum(route.custo for route in routes)
        return Solution(
            instance_nome=self.inst.nome,
            algoritmo="ga",
            routes=routes,
            fitness=self.fitness_fn(routes),
            custo_operacional=custo_operacional,
            distancia_total_km=sum(route.distancia_km for route in routes),
            penalidades=fitness.penalties(routes),
            historico_fitness=history,
            tempo_exec_s=time.perf_counter() - start,
            seed=seed,
        )
