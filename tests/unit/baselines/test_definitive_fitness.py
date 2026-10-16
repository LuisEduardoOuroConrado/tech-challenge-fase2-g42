import pytest

from medroute.baselines import (
    solve_nearest_neighbor,
    solve_nearest_neighbor_two_opt,
    solve_random,
    solve_savings,
)
from medroute.baselines.nearest_neighbor import nearest_neighbor_order
from medroute.constraints import duracao_rota
from medroute.data.fleet import FleetConfig
from medroute.domain.models import Priority
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness

SOLVERS = [solve_nearest_neighbor, solve_nearest_neighbor_two_opt, solve_random, solve_savings]


@pytest.fixture
def definitive(instance, dm):
    inst = instance.model_copy(
        update={
            "deliveries": [
                instance.deliveries[0].model_copy(
                    update={"prioridade": Priority.CRITICA, "deadline_min": 1}
                ),
                *instance.deliveries[1:],
            ]
        }
    )
    fleet = FleetConfig(vehicles=tuple(inst.fleet), servico_min_padrao=12, jornada_max_min=20)
    return inst, fleet, make_fitness(inst, dm, fleet, load_fitness_config())


@pytest.mark.parametrize("solve", SOLVERS)
def test_fitness_definitivo_aplica_paradas_prioridade_e_penalidades_p1(definitive, dm, solve):
    inst, fleet, fitness_fn = definitive
    solution = solve(inst, dm, fitness_fn=fitness_fn)
    assert solution.fitness == pytest.approx(
        solution.custo_operacional
        + fitness_fn.priority_cost(solution.routes)
        + sum(solution.penalidades.values())
    )
    assert solution.penalidades == fitness_fn.penalties(solution.routes)
    assert solution.penalidades["deadline"] > 0
    assert solution.penalidades["jornada"] > 0
    for route in solution.routes:
        vehicle = next(vehicle for vehicle in inst.fleet if vehicle.id == route.vehicle_id)
        assert route.duracao_min == pytest.approx(
            duracao_rota(dm, vehicle, route.sequence, inst, fleet)
        )


def test_nn_usa_exatamente_o_split_do_ga(definitive, dm):
    inst, _, fitness_fn = definitive
    config = GAConfig(
        population_size=4,
        generations=2,
        crossover_rate=0.9,
        mutation_rate=0.2,
        elitism=1,
        tournament_size=2,
        crossover="ox",
        mutation="inversion",
    )
    ga = GeneticAlgorithm(inst, dm, config, fitness_fn)
    solution = solve_nearest_neighbor(inst, dm, fitness_fn=fitness_fn)
    assert solution.routes == ga.decode(nearest_neighbor_order(inst, dm))


def test_two_opt_otimiza_o_mesmo_fitness_definitivo(definitive, dm):
    inst, _, fitness_fn = definitive
    nn = solve_nearest_neighbor(inst, dm, fitness_fn=fitness_fn)
    improved = solve_nearest_neighbor_two_opt(inst, dm, fitness_fn=fitness_fn)
    assert improved.fitness <= nn.fitness
    assert improved.historico_fitness == [nn.fitness, improved.fitness]
