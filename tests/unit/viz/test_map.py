from pathlib import Path

import folium
import pytest

from medroute.data import load_fleet, load_instance
from medroute.domain.models import Solution
from medroute.viz import build_map, save_map

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def inst():
    return load_instance(
        ROOT / "data" / "instances" / "sp_15.json", load_fleet(ROOT / "configs" / "frota.yaml")
    )


@pytest.fixture
def solution():
    return Solution.model_validate_json(
        (ROOT / "tests" / "fixtures" / "solution_sp15.json").read_text(encoding="utf-8")
    )


def children_of(parent, kind):
    return [child for child in parent._children.values() if isinstance(child, kind)]


def test_uma_camada_por_rota_com_linha_e_marcadores(solution, inst):
    fmap = build_map(solution, inst)
    layers = children_of(fmap, folium.FeatureGroup)

    assert len(layers) == len(solution.routes)
    for layer, route in zip(layers, solution.routes, strict=True):
        assert route.vehicle_id in layer.layer_name
        [line] = children_of(layer, folium.PolyLine)
        assert len(line.locations) == len(route.sequence) + 2
        assert line.locations[0] == line.locations[-1]
        assert len(children_of(layer, folium.Marker)) == len(route.sequence)


def test_html_contem_deposito_e_entregas(solution, inst, tmp_path):
    path = save_map(solution, inst, tmp_path / "sub" / "mapa.html")
    html = path.read_text(encoding="utf-8")

    assert inst.depot.nome in html
    assert all(delivery.id in html for delivery in inst.deliveries)
    assert "exclamation-triangle" in html


def test_rejeita_solucao_de_outra_instancia(solution, inst):
    other = inst.model_copy(update={"nome": "sp_40"})
    with pytest.raises(ValueError):
        build_map(solution, other)
