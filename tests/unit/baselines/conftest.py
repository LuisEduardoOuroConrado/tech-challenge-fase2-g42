import pytest

from medroute.data import DistanceMatrix
from medroute.domain.models import Delivery, Depot, Instance, Vehicle


@pytest.fixture
def instance():
    return Instance(
        nome="baseline_teste",
        depot=Depot(id="dep", nome="Depósito", lat=0, lon=0),
        deliveries=[
            Delivery(
                id=identifier,
                nome=identifier,
                lat=0.01 * (index + 1),
                lon=0,
                peso_kg=10,
                volume_l=20,
                prioridade="normal",
            )
            for index, identifier in enumerate("abcd")
        ],
        fleet=[
            Vehicle(
                id="van-01",
                tipo="van",
                capacidade_kg=1000,
                capacidade_l=5000,
                autonomia_km=1000,
                velocidade_kmh=30,
                custo_fixo=100,
                custo_km=2,
            )
        ],
    )


@pytest.fixture
def dm(instance):
    class TableDistances(DistanceMatrix):
        """Matriz simétrica com NN subótimo e retorno conhecido ao depósito."""

        table = [
            [0, 1, 2, 3, 4],
            [1, 0, 1, 2, 2],
            [2, 1, 0, 1, 2],
            [3, 2, 1, 0, 10],
            [4, 2, 2, 10, 0],
        ]

        def km(self, i, j):
            return float(self.table[i][j])

        def time(self, i, j, velocidade_kmh, saida_min=None):
            return self.km(i, j) / velocidade_kmh * 60

    return TableDistances(instance)
