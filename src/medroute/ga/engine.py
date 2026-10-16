"""Motor do GA: evolução geracional com torneio, elitismo e parada por estagnação.

Opcionalmente híbrido: semente do vizinho mais próximo na população inicial e busca local
2-opt dentro de cada rota nos filhos (lamarckiana: o cromossomo melhorado substitui o filho).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from medroute.data.distance import DistanceMatrix
from medroute.domain.models import Instance, Route, Solution

from . import fitness
from .decoder import decode, split_decode
from .encoding import (
    Chromosome,
    create_population,
    nearest_neighbor_chromosome,
    validate_chromosome,
)
from .operators import (
    inversion_mutation,
    order_crossover,
    pmx_crossover,
    route_two_opt,
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
    seed_nearest_neighbor: bool = False
    local_search_rate: Rate = 0.0

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
        self._index_of = {delivery.id: i for i, delivery in enumerate(inst.deliveries, start=1)}
        self._id_of = {i: delivery_id for delivery_id, i in self._index_of.items()}
        self._km: list[list[float]] | None = None

    def decode(self, chromosome: Chromosome) -> list[Route]:
        """Split ótimo com o fitness definitivo (Spec 03); guloso com o provisório."""
        if isinstance(self.fitness_fn, fitness.Fitness):
            return split_decode(
                chromosome,
                self.inst,
                self.dm,
                self.fitness_fn.cfg,
                self.fitness_fn.servico_min,
                self.fitness_fn.fleet,
            )
        return decode(chromosome, self.inst, self.dm)

    def penalties(self, routes: list[Route]) -> dict[str, float]:
        if isinstance(self.fitness_fn, fitness.Fitness):
            return self.fitness_fn.penalties(routes)
        return fitness.penalties(routes)

    def score(self, chromosome: Chromosome) -> float:
        key = tuple(chromosome)
        if key not in self._cache:
            validate_chromosome(chromosome, self.inst)
            self._cache[key] = self.fitness_fn(self.decode(chromosome))
        return self._cache[key]

    def _mutate(self, chromosome: Chromosome, rng: random.Random) -> Chromosome:
        if self.config.mutation == "swap":
            return swap_mutation(chromosome, rng)
        if self.config.mutation == "inversion":
            return inversion_mutation(chromosome, rng)
        return two_opt_local(chromosome, self.score)

    def _local_search(self, chromosome: Chromosome) -> Chromosome:
        """2-opt em km dentro de cada rota decodificada; só fica se o fitness melhorar."""
        if self._km is None:
            self._km = self.dm.matrix().tolist()
        improved: Chromosome = []
        for route in self.decode(chromosome):
            stops = route_two_opt([self._index_of[i] for i in route.sequence], self._km)
            improved.extend(self._id_of[stop] for stop in stops)
        return improved if self.score(improved) < self.score(chromosome) else chromosome

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
                # Sem sorteio quando desligada, para não mudar resultados já publicados.
                if cfg.local_search_rate and rng.random() < cfg.local_search_rate:
                    child = self._local_search(child)
                if len(offspring) < cfg.population_size:
                    offspring.append(child)
        return offspring

    def run(self, seed: int) -> Solution:
        start = time.perf_counter()
        rng = random.Random(seed)
        cfg = self.config

        population = create_population(self.inst, cfg.population_size, rng)
        if cfg.seed_nearest_neighbor:
            population[0] = nearest_neighbor_chromosome(self.inst, self.dm)
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

        routes = self.decode(best)
        custo_operacional = sum(route.custo for route in routes)
        return Solution(
            instance_nome=self.inst.nome,
            algoritmo="ga",
            routes=routes,
            fitness=self.fitness_fn(routes),
            custo_operacional=custo_operacional,
            distancia_total_km=sum(route.distancia_km for route in routes),
            penalidades=self.penalties(routes),
            historico_fitness=history,
            tempo_exec_s=time.perf_counter() - start,
            seed=seed,
        )
