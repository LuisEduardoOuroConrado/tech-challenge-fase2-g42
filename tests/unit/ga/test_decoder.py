import pytest
from conftest import make_instance, make_vehicle

from medroute.data import DistanceMatrix
from medroute.ga import decode


def ids(inst):
    return [d.id for d in inst.deliveries]


def test_tsp_um_veiculo_gera_rota_unica_com_retorno_ao_deposito(instance, dm):
    chromosome = list(reversed(ids(instance)))
    [route] = decode(chromosome, instance, dm)

    indices = [int(i[1:]) for i in chromosome]
    expected_km = dm.route_km(indices)
    assert route.sequence == chromosome
    assert route.distancia_km == pytest.approx(expected_km)
    assert route.distancia_km > sum(dm.km(a, b) for a, b in zip(indices, indices[1:], strict=False))
    assert route.duracao_min == pytest.approx(expected_km / 30.0 * 60)
    assert route.custo == pytest.approx(100.0 + 2.0 * expected_km)
    assert route.carga_kg == pytest.approx(60.0)
    assert sum(route.violacoes.values()) == 0


def test_split_por_peso_preserva_ordem_e_nao_duplica():
    fleet = [make_vehicle(f"v{i}", capacidade_kg=25.0) for i in range(1, 4)]
    inst = make_instance(6, fleet)
    chromosome = ids(inst)
    routes = decode(chromosome, inst, DistanceMatrix(inst))

    assert [r.sequence for r in routes] == [chromosome[0:2], chromosome[2:4], chromosome[4:6]]
    assert len({r.vehicle_id for r in routes}) == 3
    assert all(r.carga_kg <= 25.0 and sum(r.violacoes.values()) == 0 for r in routes)


def test_split_por_volume():
    fleet = [make_vehicle(f"v{i}", capacidade_l=70.0) for i in range(1, 3)]
    inst = make_instance(6, fleet)
    routes = decode(ids(inst), inst, DistanceMatrix(inst))
    assert [len(r.sequence) for r in routes] == [3, 3]


def test_split_por_autonomia():
    inst = make_instance(6)
    dm = DistanceMatrix(inst)
    limite = dm.route_km([1, 2, 3]) + 0.01
    fleet = [make_vehicle(f"v{i}", autonomia_km=limite) for i in range(1, 4)]
    inst = inst.model_copy(update={"fleet": fleet})
    routes = decode(ids(inst), inst, dm)
    assert routes[0].sequence == ["e01", "e02", "e03"]
    assert routes[0].violacoes["autonomia"] == 0
    assert dm.route_km([1, 2, 3, 4]) > limite


def test_escolhe_veiculo_mais_barato_que_comporta_a_rota():
    fleet = [
        make_vehicle("van", custo_fixo=200.0),
        make_vehicle("moto", capacidade_kg=100.0, custo_fixo=60.0, custo_km=0.5),
    ]
    inst = make_instance(3, fleet)
    [route] = decode(ids(inst), inst, DistanceMatrix(inst))
    assert route.vehicle_id == "moto"


def test_refrigerado_nao_vai_em_veiculo_que_nao_aceita():
    fleet = [
        make_vehicle("moto", custo_fixo=10.0, aceita_refrigerado=False),
        make_vehicle("carro", custo_fixo=100.0),
    ]
    inst = make_instance(2, fleet, refrigerado=True)
    [route] = decode(ids(inst), inst, DistanceMatrix(inst))
    assert route.vehicle_id == "carro"
    assert route.violacoes["compatibilidade"] == 0


def test_frota_insuficiente_mantem_entregas_e_registra_violacao():
    fleet = [make_vehicle("v1", capacidade_kg=25.0), make_vehicle("v2", capacidade_kg=25.0)]
    inst = make_instance(6, fleet)
    routes = decode(ids(inst), inst, DistanceMatrix(inst))

    assert sorted(i for r in routes for i in r.sequence) == ids(inst)
    assert len(routes) == 2
    assert routes[-1].violacoes["capacidade"] > 0


def test_entrega_maior_que_a_frota_permanece_com_violacao():
    inst = make_instance(1, [make_vehicle(capacidade_kg=5.0)])
    [route] = decode(ids(inst), inst, DistanceMatrix(inst))
    assert route.sequence == ["e01"]
    assert route.violacoes["capacidade"] == pytest.approx(1.0)


def test_decoder_e_deterministico_e_rejeita_cromossomo_invalido(instance, dm):
    chromosome = ids(instance)
    assert decode(chromosome, instance, dm) == decode(chromosome, instance, dm)
    with pytest.raises(ValueError):
        decode(chromosome[:-1], instance, dm)
