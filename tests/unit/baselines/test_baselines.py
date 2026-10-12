import random

import pytest

from medroute.baselines import (
    solve_nearest_neighbor,
    solve_nearest_neighbor_two_opt,
    solve_random,
)
from medroute.data import DistanceMatrix
from medroute.domain.models import Solution
from medroute.ga import fitness

SOLVERS = [solve_nearest_neighbor, solve_nearest_neighbor_two_opt, solve_random]


@pytest.mark.parametrize("solve", SOLVERS)
def test_solution_preserva_entregas_entrada_e_contrato(instance, dm, solve):
    original = instance.model_dump_json()
    solution = solve(instance, dm, seed=17)
    assert sorted(stop for route in solution.routes for stop in route.sequence) == list("abcd")
    assert solution.seed == 17
    assert solution.instance_nome == instance.nome
    assert solution.fitness == fitness.evaluate(solution.routes)
    assert solution.custo_operacional == sum(route.custo for route in solution.routes)
    assert solution.distancia_total_km == sum(route.distancia_km for route in solution.routes)
    assert Solution.model_validate_json(solution.model_dump_json()) == solution
    assert instance.model_dump_json() == original


def test_nn_escolhe_vizinho_mais_proximo_e_conta_retorno(instance, dm):
    solution = solve_nearest_neighbor(instance, dm)
    route = solution.routes[0]
    assert route.sequence == list("abcd")
    assert route.distancia_km == 17  # dep-a-b-c-d-dep: 1 + 1 + 1 + 10 + 4
    assert route.duracao_min == 34
    assert route.custo == 134
    assert route.carga_kg == 40
    assert route.carga_l == 80


def test_nn_desempata_por_id_mesmo_com_ordem_de_entrada_diferente(instance):
    first, second = instance.deliveries[:2]
    tied = first.model_copy(update={"id": "z"})
    other = first.model_copy(update={"id": "a"})
    inst = instance.model_copy(update={"deliveries": [tied, other, second]})
    solution = solve_nearest_neighbor(inst, DistanceMatrix(inst))
    assert solution.routes[0].sequence[:2] == ["a", "z"]


def test_two_opt_melhora_nn_e_registra_fitness_inicial(instance, dm):
    nn = solve_nearest_neighbor(instance, dm)
    improved = solve_nearest_neighbor_two_opt(instance, dm)
    assert improved.fitness < nn.fitness
    assert improved.historico_fitness == [nn.fitness, improved.fitness]


@pytest.mark.parametrize("solve", SOLVERS)
def test_seed_reproduz_solucao_exceto_tempo(instance, dm, solve):
    first = solve(instance, dm, seed=7).model_dump(exclude={"tempo_exec_s"})
    second = solve(instance, dm, seed=7).model_dump(exclude={"tempo_exec_s"})
    assert first == second


def test_aleatorio_nao_altera_rng_global_e_varia_entre_seeds(instance, dm):
    state = random.getstate()
    sequences = {
        tuple(solve_random(instance, dm, seed=seed).routes[0].sequence) for seed in range(5)
    }
    assert random.getstate() == state
    assert len(sequences) > 1


@pytest.mark.parametrize("solve", SOLVERS)
def test_uma_entrega_tem_ida_e_volta(instance, solve):
    inst = instance.model_copy(update={"deliveries": instance.deliveries[:1]})
    dm = DistanceMatrix(inst)
    solution = solve(inst, dm)
    assert solution.routes[0].sequence == ["a"]
    assert solution.distancia_total_km == pytest.approx(2 * dm.km(0, 1))


@pytest.mark.parametrize("solve", SOLVERS)
def test_decoder_compartilhado_separa_rotas_por_capacidade(instance, dm, solve):
    vehicles = [
        instance.fleet[0].model_copy(update={"id": f"v{i}", "capacidade_kg": 20}) for i in range(2)
    ]
    inst = instance.model_copy(update={"fleet": vehicles})
    solution = solve(inst, dm)
    assert len(solution.routes) == 2
    assert all(route.carga_kg <= 20 for route in solution.routes)
    assert sum(solution.penalidades.values()) == 0


@pytest.mark.parametrize("solve", SOLVERS)
def test_frota_insuficiente_preserva_entregas_e_registra_violacao(instance, dm, solve):
    vehicle = instance.fleet[0].model_copy(update={"capacidade_kg": 1})
    inst = instance.model_copy(update={"fleet": [vehicle]})
    solution = solve(inst, dm)
    assert sorted(solution.routes[0].sequence) == list("abcd")
    assert solution.routes[0].violacoes["capacidade"] > 0
    assert solution.penalidades["capacidade"] > 0


@pytest.mark.parametrize("solve", SOLVERS)
def test_aceita_mesma_funcao_fitness_do_ga(instance, dm, solve):
    def evaluate(routes):
        return sum(route.distancia_km for route in routes)

    solution = solve(instance, dm, fitness_fn=evaluate)
    assert solution.fitness == solution.distancia_total_km


@pytest.mark.parametrize("passes", [0, -1])
def test_two_opt_rejeita_limite_invalido(instance, dm, passes):
    with pytest.raises(ValueError, match="max_passes"):
        solve_nearest_neighbor_two_opt(instance, dm, max_passes=passes)


def test_two_opt_nao_piora_quando_nao_existe_melhoria(instance, dm):
    solution = solve_nearest_neighbor_two_opt(instance, dm, fitness_fn=lambda routes: 10)
    assert solution.routes[0].sequence == list("abcd")
    assert solution.historico_fitness == [10, 10]
