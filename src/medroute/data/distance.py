"""Matriz de distâncias: haversine x fator de tortuosidade (ADR 0003).

Determinística e offline. Índice 0 = depósito; i>=1 = entrega i.
"""
from __future__ import annotations

import math
from itertools import pairwise

import numpy as np

R_TERRA_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_TERRA_KM * math.asin(math.sqrt(a))


def _hhmm_to_min(s: str) -> float:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


class DistanceMatrix:
    def __init__(self, instance, fleet=None, fator_tortuosidade: float | None = None):
        self.instance = instance
        if fator_tortuosidade is None:
            fator_tortuosidade = fleet.fator_tortuosidade if fleet else 1.30
        self.fator = fator_tortuosidade
        self.transito = list(fleet.transito) if fleet else []
        self.inicio_jornada_min = _hhmm_to_min(fleet.inicio_jornada) if fleet else 420.0
        pts = [(instance.depot.lat, instance.depot.lon)] + [
            (e.lat, e.lon) for e in instance.deliveries
        ]
        n = len(pts)
        d = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d[i, j] = d[j, i] = haversine_km(*pts[i], *pts[j]) * self.fator
        self._km = d

    @property
    def size(self) -> int:
        return self._km.shape[0]

    def km(self, i: int, j: int) -> float:
        return float(self._km[i, j])

    def matrix(self) -> np.ndarray:
        return self._km.copy()

    def route_km(self, rota: list[int]) -> float:
        """Distância de depósito -> rota -> depósito (rota sem o 0)."""
        if not rota:
            return 0.0
        seq = [0, *rota, 0]
        return float(sum(self._km[a, b] for a, b in pairwise(seq)))

    def fator_transito(self, minuto_do_dia: float | None) -> float:
        if minuto_do_dia is None or not self.transito:
            return 1.0
        for p in self.transito:
            if _hhmm_to_min(p["inicio"]) <= minuto_do_dia % 1440 < _hhmm_to_min(p["fim"]):
                return float(p["fator"])
        return 1.0

    def time(self, i: int, j: int, velocidade_kmh: float, saida_min: float | None = None) -> float:
        """Tempo de viagem em minutos. `saida_min` = minuto do dia da partida
        (None = sem fator de trânsito, P0). Fator de trânsito é P1."""
        if velocidade_kmh <= 0:
            raise ValueError("velocidade deve ser > 0")
        base = self._km[i, j] / velocidade_kmh * 60.0
        return base * self.fator_transito(saida_min)
