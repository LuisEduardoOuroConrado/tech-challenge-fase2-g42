import random
from dataclasses import replace

import pytest

from medroute.baselines import solve_savings
from medroute.baselines.savings import savings_chains, savings_order
from medroute.data import DistanceMatrix
from medroute.data.fleet import FleetConfig
from medroute.domain.models import VehicleType
from medroute.ga import load_fitness_config, make_fitness


def test_savings_economiza_distancia_conhecida_e_fecha_circuito(instance, dm):
    # Savings(b,c)=4; Savings(b,d)=4; Savings(a,d)=3: a-d-b-c, 9 km.
    solution = solve_savings(instance, dm)
    assert solution.routes[0].sequence == list("adbc")
    assert solution.distancia_total_km == 9
    assert solution.custo_operacional == 118
    assert solution.historico_fitness == [118]


def test_economias_nao_positivas_nao_fundem_rotas(instance, dm):
    for i in range(1, 5):
        for j in range(i + 1, 5):
            dm.table[i][j] = dm.table[j][i] = dm.table[0][i] + dm.table[0][j] + 1
    assert savings_order(instance, dm) == list("abcd")


@pytest.mark.parametrize("limit", [{"capacidade_kg": 10}, {"capacidade_l": 20}])
def test_fusao_respeita_kg_e_litros(instance, dm, limit):
    inst = instance.model_copy(update={"fleet": [instance.fleet[0].model_copy(update=limit)]})
    assert savings_order(inst, dm) == list("abcd")  # Só cabem rotas unitárias.


def test_fusao_inclui_volta_na_autonomia(instance, dm):
    inst = instance.model_copy(
        update={"fleet": [instance.fleet[0].model_copy(update={"autonomia_km": 8})]}
    )
    # A cadeia completa mede 9 km; cada cadeia aceita precisa caber nos 8 km.
    chains = savings_chains(inst, dm)
    assert len(chains) > 1
    indexes = {delivery.id: i for i, delivery in enumerate(inst.deliveries, start=1)}
    for chain in chains:
        legs = [0, *(indexes[stop] for stop in chain), 0]
        assert sum(dm.km(a, b) for a, b in zip(legs, legs[1:], strict=False)) <= 8


def test_desempate_nao_depende_da_ordem_das_entregas(instance):
    deliveries = [delivery.model_copy(update={"lat": 0.01}) for delivery in instance.deliveries]
    inst = instance.model_copy(update={"deliveries": deliveries})
    reversed_inst = inst.model_copy(update={"deliveries": deliveries[::-1]})
    assert savings_order(inst, DistanceMatrix(inst)) == savings_order(
        reversed_inst, DistanceMatrix(reversed_inst)
    )


def test_savings_nao_modifica_rng_global(instance, dm):
    before = random.getstate()
    solve_savings(instance, dm, seed=101)
    assert random.getstate() == before


@pytest.mark.parametrize("refrigerated", [True, False])
def test_fusao_exige_veiculo_compativel_com_refrigerado_e_volumoso(instance, dm, refrigerated):
    moto = instance.fleet[0].model_copy(
        update={"tipo": VehicleType.MOTO, "aceita_refrigerado": False}
    )
    inst = instance.model_copy(
        update={
            "fleet": [moto],
            "deliveries": [
                delivery.model_copy(update={"refrigerado": refrigerated})
                for delivery in instance.deliveries
            ],
        }
    )
    fleet = FleetConfig(vehicles=(moto,), volumoso_limiar_l=10, tipos_sem_volumoso={"moto"})
    if refrigerated:
        fleet = replace(fleet, tipos_sem_volumoso=frozenset())
    fitness_fn = make_fitness(inst, dm, fleet, load_fitness_config())
    assert savings_order(inst, dm, fitness_fn) == list("abcd")
    solution = solve_savings(inst, dm, fitness_fn=fitness_fn)
    assert sorted(stop for route in solution.routes for stop in route.sequence) == list("abcd")
    assert solution.penalidades["compatibilidade"] > 0
