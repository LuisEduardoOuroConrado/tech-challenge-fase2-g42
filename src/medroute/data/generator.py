"""Gerador de instâncias (seed fixa). Depósito = farmácia central do HC-FMUSP.

ATENÇÃO: coordenadas das unidades reais são aproximadas (~100 m) e devem ser
conferidas no Google Maps/CNES antes do relatório (registrar fonte no PR).
"""
from __future__ import annotations

import math
import random

from medroute.domain.models import Delivery, Depot, Instance, Priority

from .fleet import FleetConfig

DEPOT = Depot(id="deposito", nome="Farmácia Central HC-FMUSP", lat=-23.5559, lon=-46.6693)

# (nome, lat, lon)  -- 10 unidades reais da rede
REAL_UNITS = [
    ("InCor", -23.5568, -46.6708),
    ("ICESP", -23.5583, -46.6699),
    ("IPq HC-FMUSP", -23.5563, -46.6712),
    ("Instituto da Criança (ICr)", -23.5571, -46.6718),
    ("IOT HC-FMUSP", -23.5544, -46.6694),
    ("Instituto de Radiologia (InRad)", -23.5575, -46.6684),
    ("HU-USP", -23.5662, -46.7357),
    ("UBS Butantã (ref.)", -23.5712, -46.7275),
    ("UBS Vila Mariana (ref.)", -23.5896, -46.6366),
    ("UBS Jardim Paulistano (ref.)", -23.5690, -46.6990),
]
# Unidades com "(ref.)" são UBS de referência: trocar pelo nome/endereço oficial (CNES) ao conferir.
RAIO_KM = 15.0


def _ponto_no_raio(rng: random.Random, centro, raio_km: float):
    r = raio_km * math.sqrt(rng.random())
    ang = rng.uniform(0, 2 * math.pi)
    dlat = (r * math.cos(ang)) / 111.32
    dlon = (r * math.sin(ang)) / (111.32 * math.cos(math.radians(centro.lat)))
    return centro.lat + dlat, centro.lon + dlon


def _carga(rng: random.Random, unidade: bool, refrigerado: bool):
    escala = 1.0 if unidade else 0.25   # domicílio = carga menor
    peso = round(rng.uniform(2, 14) * escala, 1)
    volume = round(rng.uniform(5, 45) * escala * (1.6 if unidade else 1.0), 1)
    if refrigerado:
        volume = max(volume, 6.0)
    # ~25% das unidades têm item volumoso (> 60 L) -> moto não leva
    if unidade and rng.random() < 0.25:
        volume = round(rng.uniform(65, 120), 1)
        peso = round(max(peso, rng.uniform(15, 40)), 1)
    return max(peso, 0.5), volume


def generate_instance(nome: str, n_total: int, n_real: int, fleet: FleetConfig | None = None,
                      seed: int = 42, raio_km: float = RAIO_KM) -> Instance:
    """n_total entregas (sem o depósito): n_real unidades reais + o resto domicílios
    sintéticos num raio de `raio_km` do depósito. Mesma seed => mesma instância.
    `fleet` (opcional) inclui a frota na instância; sem ele, usa a frota de configs/frota.yaml."""
    from .distance import haversine_km
    from .loader import load_fleet

    if n_real > n_total:
        raise ValueError("n_real não pode exceder n_total")
    fleet = fleet or load_fleet()
    rng = random.Random(seed)
    reais = [u for u in REAL_UNITS
             if haversine_km(DEPOT.lat, DEPOT.lon, u[1], u[2]) <= raio_km]
    if n_real > len(reais):
        raise ValueError(f"só há {len(reais)} unidades reais dentro do raio")

    meta = [(nm, lat, lon, True) for nm, lat, lon in reais[:n_real]] + [
        (f"Domicílio {k:02d}", *_ponto_no_raio(rng, DEPOT, raio_km), False)
        for k in range(1, n_total - n_real + 1)
    ]
    # Quotas exatas de prioridade/refrigeração (mix reproduzível, não só esperado)
    n_crit = round(0.15 * n_total)
    n_alta = round(0.25 * n_total)
    prios = ([Priority.CRITICA] * n_crit + [Priority.ALTA] * n_alta
             + [Priority.NORMAL] * (n_total - n_crit - n_alta))
    rng.shuffle(prios)
    ref_idx = set(rng.sample(range(n_total), max(1, round(0.10 * n_total))))

    entregas = []
    for i, (nm, lat, lon, unidade) in enumerate(meta):
        prio = prios[i]
        peso, vol = _carga(rng, unidade, i in ref_idx)
        deadline = float(rng.choice([120, 180, 240, 300])) if prio is Priority.CRITICA else None
        entregas.append(Delivery(
            id=f"entrega-{i + 1:02d}", nome=nm, lat=round(lat, 6), lon=round(lon, 6),
            peso_kg=peso, volume_l=vol, prioridade=prio, refrigerado=i in ref_idx,
            deadline_min=deadline))
    return Instance(nome=nome, depot=DEPOT, deliveries=entregas, fleet=list(fleet.vehicles))
