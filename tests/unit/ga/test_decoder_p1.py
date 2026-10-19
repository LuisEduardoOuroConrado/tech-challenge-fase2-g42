"""Decoder com `fleet` (P1, Spec 03 seção 3): volumoso, deadline, jornada e tempo de parada."""

import pytest
from conftest import make_instance, make_vehicle

from medroute.constraints import cronograma_rota, duracao_rota
from medroute.data import DistanceMatrix, FleetConfig
from medroute.domain.models import Priority
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness
from medroute.ga.decoder import _feasible_segments, decode, split_decode

CFG = load_fitness_config()


def ids(inst) -> list[str]:
    return [d.id for d in inst.deliveries]


def update(inst, changes: dict[str, dict]):
    deliveries = [d.model_copy(update=changes.get(d.id, {})) for d in inst.deliveries]
    return inst.model_copy(update={"deliveries": deliveries})


def setup(inst, **fleet_args):
    fleet = FleetConfig(vehicles=tuple(inst.fleet), **fleet_args)
    dm = DistanceMatrix(inst)
    return dm, fleet, make_fitness(inst, dm, fleet, CFG)


def critica(deadline_min: float) -> dict:
    return {"prioridade": Priority.CRITICA, "deadline_min": deadline_min}


def test_sem_fleet_mantem_o_p0():
    inst = make_instance(4)
    dm, _, _ = setup(inst)
    [route] = decode(ids(inst), inst, dm)
    assert set(route.violacoes) == {"capacidade", "autonomia", "compatibilidade"}
    v = inst.fleet[0].velocidade_kmh
    assert route.duracao_min == pytest.approx(
        sum(dm.time(a, b, v) for a, b in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)])
    )


def test_com_fleet_duracao_soma_paradas_e_registra_deadline_e_jornada():
    inst = make_instance(4)
    dm, fleet, _ = setup(inst)
    [route] = decode(ids(inst), inst, dm, fleet)
    vehicle = inst.fleet[0]
    assert route.duracao_min == pytest.approx(duracao_rota(dm, vehicle, ids(inst), inst, fleet))
    assert set(route.violacoes) == {
        "capacidade",
        "autonomia",
        "compatibilidade",
        "deadline",
        "jornada",
    }
    assert not any(route.violacoes.values())


def test_volumoso_em_veiculo_sem_volumoso_e_incompatibilidade():
    inst = make_instance(2, fleet=[make_vehicle("moto-01", tipo="moto")])
    inst = update(inst, {"e01": {"volume_l": 80.0}})
    dm, fleet, _ = setup(inst, tipos_sem_volumoso=frozenset({"moto"}))
    [route] = decode(ids(inst), inst, dm, fleet)
    assert route.violacoes["compatibilidade"] == 1
    # sem fleet o volumoso não é verificado (P0)
    [p0] = decode(ids(inst), inst, dm)
    assert p0.violacoes["compatibilidade"] == 0


def test_split_manda_o_volumoso_para_quem_aceita():
    barata = {"tipo": "moto", "custo_fixo": 0.0, "custo_km": 0.0}
    fleet = [make_vehicle("moto-01", **barata), make_vehicle("van-01")]
    inst = update(make_instance(3, fleet=fleet), {"e02": {"volume_l": 80.0}})
    dm, fleet_cfg, fitness = setup(inst, tipos_sem_volumoso=frozenset({"moto"}))
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min, fleet_cfg)
    rota_do_volumoso = next(r for r in routes if "e02" in r.sequence)
    assert rota_do_volumoso.vehicle_id == "van-01"
    assert sum(fitness.penalties(routes).values()) == 0


def test_deadline_registra_os_minutos_de_atraso():
    inst = update(make_instance(3), {"e03": critica(1.0)})
    dm, fleet, fitness = setup(inst)
    [route] = decode(ids(inst), inst, dm, fleet)
    chegada = cronograma_rota(dm, inst.fleet[0], ids(inst), inst, fleet)["e03"]
    assert route.violacoes["deadline"] == pytest.approx(chegada - 1.0)
    assert fitness.penalties([route])["deadline"] == pytest.approx(10 * (chegada - 1.0))


def test_jornada_registra_os_minutos_acima_do_limite():
    inst = make_instance(4)
    dm, fleet, fitness = setup(inst, jornada_max_min=30.0)
    [route] = decode(ids(inst), inst, dm, fleet)
    assert route.violacoes["jornada"] == pytest.approx(route.duracao_min - 30.0)
    assert fitness.penalties([route])["jornada"] == pytest.approx(5 * (route.duracao_min - 30.0))


def test_split_divide_a_rota_para_cumprir_a_jornada():
    gratis = {"custo_fixo": 0.0, "custo_km": 0.0}
    fleet = [make_vehicle("van-01", **gratis), make_vehicle("van-02", **gratis)]
    inst = make_instance(6, fleet=fleet)
    dm, fleet_cfg, fitness = setup(inst, jornada_max_min=60.0)
    [inteira] = decode(ids(inst), inst, dm, fleet_cfg)
    assert inteira.duracao_min > 60.0  # uma rota só estoura a jornada
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min, fleet_cfg)
    assert len(routes) == 2
    assert fitness(routes) < fitness([inteira])


def test_custo_do_split_com_fleet_bate_com_o_fitness():
    fleet = [
        make_vehicle("moto-01", tipo="moto", capacidade_kg=30.0, custo_fixo=20.0, custo_km=0.8),
        make_vehicle("van-01"),
    ]
    inst = update(make_instance(7, fleet=fleet), {"e05": critica(20.0), "e03": {"volume_l": 80}})
    dm, fleet_cfg, fitness = setup(inst, tipos_sem_volumoso=frozenset({"moto"}))
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min, fleet_cfg)
    assert [d for r in routes for d in r.sequence] == ids(inst)
    assert fitness(routes) <= fitness(decode(ids(inst), inst, dm, fleet_cfg)) + 1e-9


def test_ga_com_fitness_definitivo_usa_o_decoder_p1():
    inst = update(make_instance(5), {"e02": {"volume_l": 80.0}})
    dm, fleet, fitness = setup(inst)
    config = GAConfig(
        population_size=6,
        generations=2,
        crossover_rate=0.9,
        mutation_rate=0.2,
        elitism=1,
        tournament_size=2,
        crossover="ox",
        mutation="swap",
    )
    ga = GeneticAlgorithm(inst, dm, config, fitness_fn=fitness)
    assert all("jornada" in r.violacoes for r in ga.decode(ids(inst)))


# Fator de trânsito (P1): todas as rotas saem em `inicio_jornada`. A faixa curta e forte faz
# o fator mudar no meio da rota, o caso em que o split e o cronograma poderiam divergir.
TRANSITO = ({"inicio": "07:00", "fim": "07:20", "fator": 3.0},)


def setup_transito(inst, **fleet_args):
    fleet = FleetConfig(vehicles=tuple(inst.fleet), transito=TRANSITO, **fleet_args)
    dm = DistanceMatrix(inst, fleet)
    return dm, fleet, make_fitness(inst, dm, fleet, CFG)


def test_saida_das_rotas_e_o_inicio_da_jornada_so_com_transito():
    vehicles = (make_vehicle("van-01"),)
    assert FleetConfig(vehicles=vehicles, transito=TRANSITO).saida_min == 7 * 60
    cedo = FleetConfig(vehicles=vehicles, transito=TRANSITO, inicio_jornada="06:30")
    assert cedo.saida_min == 390
    assert FleetConfig(vehicles=vehicles).saida_min is None


def test_decoder_aplica_o_transito_na_duracao_e_nas_chegadas():
    inst = update(make_instance(4), {"e04": critica(1.0)})
    dm, fleet, _ = setup_transito(inst)
    [route] = decode(ids(inst), inst, dm, fleet)
    vehicle = inst.fleet[0]
    assert route.duracao_min == pytest.approx(
        duracao_rota(dm, vehicle, ids(inst), inst, fleet, saida_min=7 * 60)
    )
    chegada = cronograma_rota(dm, vehicle, ids(inst), inst, fleet, saida_min=7 * 60)["e04"]
    assert route.violacoes["deadline"] == pytest.approx(chegada - 1.0)
    [sem_transito] = decode(ids(inst), inst, *setup(inst)[:2])
    assert route.duracao_min > sem_transito.duracao_min


def test_custo_do_split_com_transito_bate_com_o_fitness():
    inst = update(make_instance(6), {"e05": critica(15.0)})
    dm, fleet, fitness = setup_transito(inst, jornada_max_min=60.0)
    [route] = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min, fleet)
    weights = [CFG.prioridade_rs_min[d.prioridade] for d in inst.deliveries]
    segments = _feasible_segments(
        inst.fleet[0],
        list(range(1, 7)),
        list(inst.deliveries),
        weights,
        dm.matrix().tolist(),
        fitness.servico_min,
        CFG,
        fleet,
        dm,
    )
    custo_no_split = dict(segments[0])[6]
    assert custo_no_split == pytest.approx(fitness([route]))
