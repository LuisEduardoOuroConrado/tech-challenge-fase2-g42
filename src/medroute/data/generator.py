"""Gerador de instâncias (seed fixa). Depósito = farmácia central do HC-FMUSP.

Coordenadas: ver docs/fontes-frota.md (seção 3). Todas vêm de fonte pública
(IBGE via CEP em ruacep.com.br; Wikipédia para o complexo do HC), com precisão de
rua/CEP (centenas de metros). Unidades no mesmo complexo compartilham o ponto.
"""
from __future__ import annotations

import math
import random

from medroute.domain.models import Delivery, Depot, Instance, Priority

from .fleet import FleetConfig

# Complexo HC-FMUSP: ajustado no Google Maps (Beatriz, 16/10)
DEPOT = Depot(id="deposito", nome="Farmácia Central HC-FMUSP", lat=-23.55770, lon=-46.66893)

# (nome, lat, lon): 10 unidades reais da rede HC-FMUSP. Endereços e fontes: docs/fontes-frota.md.
# A ordem importa: sp_15 usa as 4 primeiras e os testes do módulo LLM dependem desses nomes.
REAL_UNITS = [
    ("InCor", -23.55695, -46.66814),                       # Enéas C. Aguiar, 44
    ("ICESP", -23.55591, -46.66817),                       # Dr. Arnaldo, 251
    ("IPq HC-FMUSP", -23.55906, -46.67080),                # R. Ovídio P. de Campos, 785
    ("Instituto da Criança (ICr)", -23.55552, -46.67318),  # Enéas C. Aguiar, 647
    ("HU-USP", -23.56494, -46.74057),                      # Lineu Prestes, 2565
    ("Hospital Auxiliar de Cotoxó", -23.53617, -46.68823),  # R. Cotoxó, 1142
    ("IMREA Lapa", -23.52162, -46.69779),                  # R. Guaicurus, 1274
    ("IOT HC-FMUSP", -23.55782, -46.67117),                # R. Ovídio P. de Campos, 333
    ("Instituto de Radiologia (InRad)", -23.55660, -46.67050),  # R. Ovídio P. de Campos
    ("Instituto Central (ICHC)", -23.55771, -46.66892),    # Enéas C. Aguiar, 255
]
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
