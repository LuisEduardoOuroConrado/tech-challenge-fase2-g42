from pathlib import Path

import pytest

from medroute.constraints import (
    CHAVES,
    cronograma_rota,
    custo_prioridade,
    duracao_rota,
    violacao_autonomia,
    violacao_capacidade,
    violacao_compatibilidade,
    violacao_deadline,
    violacao_jornada,
)
from medroute.data import DistanceMatrix, FleetConfig, load_fleet, load_instance
from medroute.domain.models import Delivery, Depot, Instance, Priority, Vehicle

ROOT = Path(__file__).resolve().parents[3]
TRANSITO = (
    {"inicio": "06:00", "fim": "09:00", "fator": 1.4},
    {"inicio": "09:00", "fim": "17:00", "fator": 1.0},
    {"inicio": "17:00", "fim": "20:00", "fator": 1.5},
)


def vehicle(vehicle_id: str = "moto-01", **overrides) -> Vehicle:
    data = {
        "id": vehicle_id,
        "tipo": "moto",
        "capacidade_kg": 15.0,
        "capacidade_l": 40.0,
        "autonomia_km": 120.0,
        "velocidade_kmh": 30.0,
        "custo_km": 0.8,
        "custo_fixo": 60.0,
        "aceita_refrigerado": False,
    }
    data.update(overrides)
    return Vehicle(**data)


def delivery(i: int, **overrides) -> Delivery:
    data = {
        "id": f"e{i:02d}",
        "nome": f"Entrega {i}",
        "lat": -23.55 + 0.01 * i,
        "lon": -46.63 + 0.005 * (i % 3),
        "peso_kg": 5.0,
        "volume_l": 10.0,
        "prioridade": Priority.NORMAL,
    }
    data.update(overrides)
    return Delivery(**data)


def instance(n: int = 3, fleet: list[Vehicle] | None = None) -> Instance:
    return Instance(
        nome="teste",
        depot=Depot(id="dep", nome="Depósito", lat=-23.55, lon=-46.63),
        deliveries=[delivery(i) for i in range(1, n + 1)],
        fleet=fleet or [vehicle()],
    )


# --- capacidade -------------------------------------------------------------------------------


def test_capacidade_zero_quando_cabe_e_no_limite_exato():
    moto = vehicle()
    assert violacao_capacidade(moto, []) == 0
    assert violacao_capacidade(moto, [delivery(1, peso_kg=5.0), delivery(2, peso_kg=5.0)]) == 0
    assert violacao_capacidade(moto, [delivery(1, peso_kg=15.0, volume_l=40.0)]) == 0


def test_capacidade_excesso_em_fracao():
    moto = vehicle()
    assert violacao_capacidade(moto, [delivery(1, peso_kg=30.0)]) == pytest.approx(1.0)
    assert violacao_capacidade(moto, [delivery(1, peso_kg=16.5)]) == pytest.approx(0.1)


def test_capacidade_soma_excesso_de_peso_e_de_volume():
    moto = vehicle()
    entregas = [delivery(1, peso_kg=30.0, volume_l=60.0)]  # +100 % de kg, +50 % de L
    assert violacao_capacidade(moto, entregas) == pytest.approx(1.5)


# --- autonomia --------------------------------------------------------------------------------


def test_autonomia_zero_abaixo_e_no_limite_exato():
    moto = vehicle(autonomia_km=120.0)
    assert violacao_autonomia(moto, 0.0) == 0
    assert violacao_autonomia(moto, 119.9) == 0
    assert violacao_autonomia(moto, 120.0) == 0


def test_autonomia_km_acima_do_limite():
    assert violacao_autonomia(vehicle(autonomia_km=120.0), 125.0) == pytest.approx(5.0)


# --- compatibilidade --------------------------------------------------------------------------


def test_compatibilidade_conta_refrigerado_e_volumoso_na_moto():
    fleet = FleetConfig(vehicles=(), tipos_sem_volumoso=frozenset({"moto"}))
    moto = vehicle()
    entregas = [
        delivery(1, refrigerado=True),
        delivery(2, volume_l=70.0),
        delivery(3),
    ]
    assert violacao_compatibilidade(fleet, moto, entregas) == 2.0


def test_compatibilidade_zero_em_carro_e_no_limiar_de_volumoso():
    fleet = FleetConfig(vehicles=(), tipos_sem_volumoso=frozenset({"moto"}))
    carro = vehicle("carro-01", tipo="carro", aceita_refrigerado=True)
    moto = vehicle()
    entregas = [delivery(1, refrigerado=True), delivery(2, volume_l=70.0)]
    assert violacao_compatibilidade(fleet, carro, entregas) == 0
    # volume exatamente no limiar (60 L) ainda não é volumoso
    assert violacao_compatibilidade(fleet, moto, [delivery(1, volume_l=60.0)]) == 0
    assert violacao_compatibilidade(fleet, moto, []) == 0


def test_compatibilidade_nao_cobra_o_excesso_de_carga_de_novo():
    fleet = FleetConfig(vehicles=(), tipos_sem_volumoso=frozenset({"moto"}))
    pesada = delivery(1, peso_kg=500.0)  # não cabe, mas é compatível: quem cobra é a capacidade
    assert violacao_compatibilidade(fleet, vehicle(), [pesada]) == 0
    assert violacao_capacidade(vehicle(), [pesada]) > 0


# --- deadline ---------------------------------------------------------------------------------


def critica(i: int, deadline: float) -> Delivery:
    return delivery(i, prioridade=Priority.CRITICA, deadline_min=deadline)


def test_deadline_zero_antes_e_no_minuto_exato():
    entregas = [critica(1, 100.0)]
    assert violacao_deadline({"e01": 60.0}, entregas) == 0
    assert violacao_deadline({"e01": 100.0}, entregas) == 0


def test_deadline_soma_os_minutos_de_atraso():
    entregas = [critica(1, 100.0), critica(2, 200.0), critica(3, 300.0)]
    chegadas = {"e01": 130.0, "e02": 250.0, "e03": 290.0}
    assert violacao_deadline(chegadas, entregas) == pytest.approx(30.0 + 50.0)


def test_deadline_ignora_entrega_sem_deadline():
    entregas = [delivery(1), critica(2, 100.0)]
    assert violacao_deadline({"e01": 10_000.0, "e02": 90.0}, entregas) == 0


# --- jornada ----------------------------------------------------------------------------------


def test_jornada_zero_e_excesso_em_minutos():
    fleet = FleetConfig(vehicles=(), jornada_max_min=480.0)
    assert violacao_jornada(0.0, fleet) == 0
    assert violacao_jornada(479.0, fleet) == 0
    assert violacao_jornada(480.0, fleet) == 0
    assert violacao_jornada(500.0, fleet) == pytest.approx(20.0)


# --- custo de prioridade ----------------------------------------------------------------------


PESOS = {Priority.CRITICA: 0.50, Priority.ALTA: 0.15, Priority.NORMAL: 0.05}


def test_custo_prioridade_pondera_chegada_pelo_peso():
    entregas = [
        critica(1, 100.0),
        delivery(2, prioridade=Priority.ALTA),
        delivery(3),
    ]
    chegadas = {"e01": 10.0, "e02": 20.0, "e03": 30.0}
    esperado = 0.50 * 10 + 0.15 * 20 + 0.05 * 30
    assert custo_prioridade(chegadas, entregas, PESOS) == pytest.approx(esperado)


def test_custo_prioridade_muda_com_os_pesos_e_critica_primeiro_custa_menos():
    entregas = [critica(1, 100.0), delivery(2)]
    critica_primeiro = custo_prioridade({"e01": 10.0, "e02": 30.0}, entregas, PESOS)
    critica_depois = custo_prioridade({"e01": 30.0, "e02": 10.0}, entregas, PESOS)
    assert critica_primeiro < critica_depois
    dobro = {p: 2 * w for p, w in PESOS.items()}
    assert custo_prioridade({"e01": 10.0, "e02": 30.0}, entregas, dobro) == pytest.approx(
        2 * critica_primeiro
    )


def test_custo_prioridade_ignora_entrega_fora_do_cronograma():
    assert custo_prioridade({}, [delivery(1)], PESOS) == 0
    assert custo_prioridade({"e01": 40.0}, [delivery(1), delivery(2)], PESOS) == pytest.approx(2.0)


# --- cronograma e duração ---------------------------------------------------------------------


def test_cronograma_soma_viagem_e_servico_das_paradas_anteriores():
    inst = instance(3)
    fleet = FleetConfig(vehicles=tuple(inst.fleet))
    dm = DistanceMatrix(inst)
    v = inst.fleet[0].velocidade_kmh
    chegadas = cronograma_rota(dm, inst.fleet[0], ["e01", "e02", "e03"], inst, fleet)
    assert chegadas["e01"] == pytest.approx(dm.time(0, 1, v))
    assert chegadas["e02"] == pytest.approx(dm.time(0, 1, v) + 10 + dm.time(1, 2, v))
    assert chegadas["e03"] == pytest.approx(
        dm.time(0, 1, v) + dm.time(1, 2, v) + dm.time(2, 3, v) + 20
    )
    assert list(chegadas.values()) == sorted(chegadas.values())


def test_cronograma_segue_a_ordem_da_rota_e_rota_vazia():
    inst = instance(3)
    fleet = FleetConfig(vehicles=tuple(inst.fleet))
    dm = DistanceMatrix(inst)
    moto = inst.fleet[0]
    assert cronograma_rota(dm, moto, [], inst, fleet) == {}
    assert duracao_rota(dm, moto, [], inst, fleet) == 0
    ida = cronograma_rota(dm, moto, ["e01", "e03"], inst, fleet)
    volta = cronograma_rota(dm, moto, ["e03", "e01"], inst, fleet)
    assert ida["e03"] != volta["e03"]
    assert set(ida) == set(volta) == {"e01", "e03"}


def test_duracao_inclui_paradas_e_volta_ao_deposito():
    inst = instance(2)
    fleet = FleetConfig(vehicles=tuple(inst.fleet))
    dm = DistanceMatrix(inst)
    moto = inst.fleet[0]
    v = moto.velocidade_kmh
    esperado = dm.time(0, 1, v) + 10 + dm.time(1, 2, v) + 10 + dm.time(2, 0, v)
    assert duracao_rota(dm, moto, ["e01", "e02"], inst, fleet) == pytest.approx(esperado)


def test_trafego_aplica_o_fator_do_periodo_de_saida():
    inst = instance(2)
    fleet = FleetConfig(vehicles=tuple(inst.fleet), transito=TRANSITO)
    dm = DistanceMatrix(inst, fleet)
    moto = inst.fleet[0]
    v = moto.velocidade_kmh
    base = cronograma_rota(dm, moto, ["e01"], inst, fleet)["e01"]       # P0: sem trânsito
    assert base == pytest.approx(dm.time(0, 1, v))
    pico = cronograma_rota(dm, moto, ["e01"], inst, fleet, saida_min=7.5 * 60)["e01"]
    assert pico == pytest.approx(base * 1.4)
    meio_dia = cronograma_rota(dm, moto, ["e01"], inst, fleet, saida_min=12 * 60)["e01"]
    assert meio_dia == pytest.approx(base)
    assert duracao_rota(dm, moto, ["e01"], inst, fleet, saida_min=7.5 * 60) > duracao_rota(
        dm, moto, ["e01"], inst, fleet
    )


def test_trafego_muda_de_fator_ao_virar_o_periodo_durante_a_rota():
    inst = instance(2)
    fleet = FleetConfig(vehicles=tuple(inst.fleet), transito=TRANSITO)
    dm = DistanceMatrix(inst, fleet)
    moto = inst.fleet[0]
    v = moto.velocidade_kmh
    saida = 8 * 60 + 59                      # 08:59: primeiro trecho ainda no pico (x1,4)
    chegadas = cronograma_rota(dm, moto, ["e01", "e02"], inst, fleet, saida_min=saida)
    assert chegadas["e01"] == pytest.approx(dm.time(0, 1, v) * 1.4)
    # o segundo trecho sai depois das 09:00 (paradas + 10 min): fator 1,0
    segundo = chegadas["e02"] - chegadas["e01"] - fleet.servico_min_padrao
    assert segundo == pytest.approx(dm.time(1, 2, v))


def test_duracao_aplica_o_fator_do_periodo_tambem_na_volta():
    inst = instance(1)
    fleet = FleetConfig(vehicles=tuple(inst.fleet), transito=TRANSITO)
    dm = DistanceMatrix(inst, fleet)
    moto = inst.fleet[0]
    v = moto.velocidade_kmh
    saida = 16 * 60 + 55  # 16:55: a ida sai fora do pico (x1,0) e a volta já sai depois das 17:00
    esperado = dm.time(0, 1, v) + fleet.servico_min_padrao + dm.time(1, 0, v) * 1.5
    assert duracao_rota(dm, moto, ["e01"], inst, fleet, saida_min=saida) == pytest.approx(esperado)


def test_jornada_estoura_com_rota_longa():
    inst = instance(60)
    fleet = FleetConfig(vehicles=tuple(inst.fleet))
    dm = DistanceMatrix(inst)
    moto = inst.fleet[0]
    ids = [d.id for d in inst.deliveries]
    duracao = duracao_rota(dm, moto, ids, inst, fleet)
    assert duracao >= 60 * fleet.servico_min_padrao
    assert violacao_jornada(duracao, fleet) == pytest.approx(duracao - 480.0)


# --- contrato com Route.violacoes / Solution.penalidades --------------------------------------


def test_chaves_batem_com_as_do_fitness():
    from medroute.ga.fitness import PENALTY_KEYS

    assert CHAVES == PENALTY_KEYS


# --- integração com os dados reais -------------------------------------------------------------


def test_sp15_com_a_frota_do_yaml():
    fleet = load_fleet(ROOT / "configs" / "frota.yaml")
    inst = load_instance(ROOT / "data" / "instances" / "sp_15.json", fleet)
    dm = DistanceMatrix(inst, fleet)
    van = next(v for v in inst.fleet if v.tipo.value == "van")
    ids = [d.id for d in inst.deliveries]
    chegadas = cronograma_rota(dm, van, ids, inst, fleet)
    assert list(chegadas) == ids and list(chegadas.values()) == sorted(chegadas.values())
    assert violacao_capacidade(van, inst.deliveries) == 0           # 15 entregas cabem na van
    assert violacao_autonomia(van, dm.route_km([dm_i for dm_i in range(1, 16)])) == 0
    moto = inst.fleet[0]
    assert violacao_capacidade(moto, inst.deliveries) > 0           # na moto não cabem
    assert violacao_compatibilidade(fleet, moto, inst.deliveries) >= 1   # refrigerado/volumoso
