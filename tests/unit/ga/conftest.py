import pytest

from medroute.data import DistanceMatrix
from medroute.domain.models import Delivery, Depot, Instance, Vehicle


def make_vehicle(vehicle_id: str = "van-01", **overrides) -> Vehicle:
    data = {
        "id": vehicle_id,
        "tipo": "van",
        "capacidade_kg": 1000.0,
        "capacidade_l": 5000.0,
        "autonomia_km": 1000.0,
        "velocidade_kmh": 30.0,
        "custo_km": 2.0,
        "custo_fixo": 100.0,
    }
    data.update(overrides)
    return Vehicle(**data)


def make_instance(n: int = 6, fleet: list[Vehicle] | None = None, **delivery) -> Instance:
    deliveries = [
        Delivery(
            id=f"e{i:02d}",
            nome=f"Entrega {i}",
            lat=-23.55 + 0.01 * i,
            lon=-46.63 + 0.005 * (i % 3),
            peso_kg=delivery.get("peso_kg", 10.0),
            volume_l=delivery.get("volume_l", 20.0),
            prioridade="normal",
            refrigerado=delivery.get("refrigerado", False),
        )
        for i in range(1, n + 1)
    ]
    return Instance(
        nome="teste",
        depot=Depot(id="dep", nome="Depósito", lat=-23.55, lon=-46.63),
        deliveries=deliveries,
        fleet=fleet or [make_vehicle()],
    )


@pytest.fixture
def instance() -> Instance:
    return make_instance()


@pytest.fixture
def dm(instance: Instance) -> DistanceMatrix:
    return DistanceMatrix(instance)
