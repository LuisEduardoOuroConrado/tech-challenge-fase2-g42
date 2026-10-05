from pathlib import Path

import numpy as np
import pytest

from medroute.data import (
    DataError,
    DistanceMatrix,
    generate_instance,
    haversine_km,
    load_fleet,
    load_instance,
    save_instance,
    validate_instance,
)
from medroute.data.generator import DEPOT
from medroute.domain.models import Priority, VehicleType

ROOT = Path(__file__).resolve().parents[3]
FROTA = ROOT / "configs" / "frota.yaml"


@pytest.fixture(scope="module")
def fleet():
    return load_fleet(FROTA)


def test_haversine_conhecido():
    # Praça da Sé -> MASP: ~2.9 km em linha reta
    assert 2.0 < haversine_km(-23.5505, -46.6333, -23.5614, -46.6559) < 3.5
    assert haversine_km(1, 1, 1, 1) == 0


def test_frota_carrega(fleet):
    ids = [v.id for v in fleet.vehicles]
    assert ids == ["moto-01", "moto-02", "carro-01", "carro-02", "van-01"]
    moto = fleet.vehicles[0]
    assert moto.tipo is VehicleType.MOTO and not moto.aceita_refrigerado
    assert moto.custo_fixo == 60 and fleet.tipos_sem_volumoso == {"moto"}
    assert fleet.fator_tortuosidade == 1.30


def test_frota_invalida(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text("tipos:\n  moto: {quantidade: 0}\n")
    with pytest.raises(DataError):
        load_fleet(p)


def test_gerador_deterministico(fleet):
    a = generate_instance("x", 15, 4, fleet, seed=7)
    assert a == generate_instance("x", 15, 4, fleet, seed=7)
    assert a != generate_instance("x", 15, 4, fleet, seed=8)


@pytest.mark.parametrize("nome,n,n_real", [("sp_15", 15, 4), ("sp_40", 40, 10), ("sp_80", 80, 10)])
def test_mix_e_raio(fleet, nome, n, n_real):
    inst = generate_instance(nome, n, n_real, fleet, seed=42)
    validate_instance(inst, fleet)
    assert len(inst.deliveries) == n and len(inst.fleet) == 5
    prios = [d.prioridade for d in inst.deliveries]
    assert prios.count(Priority.CRITICA) == round(0.15 * n)
    assert prios.count(Priority.ALTA) == round(0.25 * n)
    assert sum(d.refrigerado for d in inst.deliveries) >= 1
    for d in inst.deliveries:
        assert haversine_km(DEPOT.lat, DEPOT.lon, d.lat, d.lon) <= 15.0 + 1e-6
        assert (d.deadline_min is not None) == (d.prioridade is Priority.CRITICA)


def test_roundtrip_json(tmp_path, fleet):
    inst = generate_instance("sp_15", 15, 4, fleet, seed=42)
    p = tmp_path / "i.json"
    save_instance(inst, p)
    assert load_instance(p, fleet) == inst


def test_instancias_commitadas_carregam(fleet):
    for nome, n in [("sp_15", 15), ("sp_40", 40), ("sp_80", 80)]:
        inst = load_instance(ROOT / "data" / "instances" / f"{nome}.json", fleet)
        assert len(inst.deliveries) == n


def test_modelo_rejeita_deadline_em_nao_critica(fleet):
    inst = generate_instance("x", 15, 4, fleet, seed=1)
    d = next(d for d in inst.deliveries if d.prioridade is Priority.NORMAL)
    with pytest.raises(ValueError):
        d.__class__(**{**d.model_dump(), "deadline_min": 30})


def test_validacao_critica_sem_deadline(fleet):
    inst = generate_instance("x", 15, 4, fleet, seed=1)
    d = next(d for d in inst.deliveries if d.prioridade is Priority.CRITICA)
    sem = d.model_copy(update={"deadline_min": None})
    outras = [x for x in inst.deliveries if x is not d]
    ruim = inst.model_copy(update={"deliveries": [sem, *outras]})
    with pytest.raises(DataError, match="crítica sem deadline"):
        validate_instance(ruim, fleet)


def test_entrega_sem_veiculo_compativel(fleet):
    inst = generate_instance("x", 15, 4, fleet, seed=1)
    gig = inst.deliveries[0].model_copy(update={"peso_kg": 5000.0})
    ruim = inst.model_copy(update={"deliveries": [gig, *inst.deliveries[1:]]})
    with pytest.raises(DataError, match="nenhum veículo"):
        validate_instance(ruim, fleet)


def test_compatibilidade_moto(fleet):
    moto, carro = fleet.vehicles[0], fleet.vehicles[2]
    inst = generate_instance("x", 15, 4, fleet, seed=1)
    base = inst.deliveries[0].model_copy(update={"peso_kg": 5.0, "volume_l": 10.0,
                                                 "refrigerado": False})
    assert fleet.aceita(moto, base)
    assert not fleet.aceita(moto, base.model_copy(update={"refrigerado": True}))
    assert not fleet.aceita(moto, base.model_copy(update={"volume_l": 80.0}))   # volumoso
    assert fleet.aceita(carro, base.model_copy(update={"volume_l": 80.0, "refrigerado": True}))


def test_matriz_propriedades(fleet):
    inst = generate_instance("sp_15", 15, 4, fleet, seed=42)
    m = DistanceMatrix(inst, fleet).matrix()
    assert m.shape == (16, 16)
    assert np.allclose(m, m.T) and np.allclose(np.diag(m), 0)
    for i in range(0, 16, 3):
        for j in range(0, 16, 4):
            for k in range(0, 16, 5):
                assert m[i, j] <= m[i, k] + m[k, j] + 1e-9


def test_matriz_aplica_fator(fleet):
    inst = generate_instance("sp_15", 15, 4, fleet, seed=42)
    d = inst.deliveries[0]
    esperado = haversine_km(inst.depot.lat, inst.depot.lon, d.lat, d.lon) * 1.30
    assert DistanceMatrix(inst, fleet).km(0, 1) == pytest.approx(esperado)


def test_rota_km_e_tempo(fleet):
    inst = generate_instance("sp_15", 15, 4, fleet, seed=42)
    dm = DistanceMatrix(inst, fleet)
    assert dm.route_km([]) == 0
    assert dm.route_km([1, 2]) == pytest.approx(dm.km(0, 1) + dm.km(1, 2) + dm.km(2, 0))
    base = dm.time(0, 1, 30)                              # P0: sem trânsito
    assert base == pytest.approx(dm.km(0, 1) / 30 * 60)
    assert dm.time(0, 1, 30, saida_min=7.5 * 60) == pytest.approx(base * 1.4)
    assert dm.time(0, 1, 30, saida_min=22 * 60) == pytest.approx(base)
    with pytest.raises(ValueError):
        dm.time(0, 1, 0)
