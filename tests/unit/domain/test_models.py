import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from medroute.domain.models import Delivery, Priority, Solution

FIXTURE = Path(__file__).parents[2] / "fixtures" / "solution_sp15.json"


def test_solution_fixture_respeita_contrato() -> None:
    solution = Solution.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    assert solution.instance_nome == "sp_15"
    assert sum(len(route.sequence) for route in solution.routes) == 15
    assert solution.distancia_total_km == pytest.approx(
        sum(route.distancia_km for route in solution.routes)
    )
    assert solution.custo_operacional == pytest.approx(
        sum(route.custo for route in solution.routes)
    )


def test_delivery_rejeita_coordenada_invalida() -> None:
    with pytest.raises(ValidationError):
        Delivery(
            id="entrega-01",
            nome="Destino",
            lat=-91,
            lon=-46.63,
            peso_kg=1,
            volume_l=1,
            prioridade=Priority.NORMAL,
        )


def test_deadline_so_pode_ser_definido_para_entrega_critica() -> None:
    with pytest.raises(ValidationError, match="entrega crítica"):
        Delivery(
            id="entrega-01",
            nome="Destino",
            lat=-23.55,
            lon=-46.63,
            peso_kg=1,
            volume_l=1,
            prioridade=Priority.ALTA,
            deadline_min=90,
        )


def test_solution_rejeita_entrega_em_duas_rotas() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["routes"][1]["sequence"].append("entrega-01")

    with pytest.raises(ValidationError, match="apenas uma rota"):
        Solution.model_validate(data)
