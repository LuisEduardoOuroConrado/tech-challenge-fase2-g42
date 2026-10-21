"""Fluxo completo da CLI encadeado, como na demo do vídeo: solve → map → instruct → report → ask."""

from pathlib import Path

from typer.testing import CliRunner

from medroute.app.cli import app
from medroute.domain.models import Solution

ROOT = Path(__file__).resolve().parents[2]
FROTA = str(ROOT / "configs" / "frota.yaml")
FITNESS = str(ROOT / "configs" / "fitness.yaml")
SP40 = str(ROOT / "data" / "instances" / "sp_40.json")

runner = CliRunner()


def _ok(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_fluxo_da_demo_em_sp40_com_llm_mock(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    _ok(
        "solve", "--inst", SP40, "--seed", "7", "--populacao", "20", "--geracoes", "10",
        "--frota", FROTA, "--fitness", FITNESS, "--out-dir", str(tmp_path), "--no-mapa",
    )  # fmt: skip
    json_path = tmp_path / "sp_40_ga_vrp_s7.json"
    solution = Solution.model_validate_json(json_path.read_text("utf-8"))
    assert sum(len(route.sequence) for route in solution.routes) == 40

    _ok("map", str(json_path), "--inst", SP40, "--frota", FROTA)
    html = json_path.with_suffix(".html").read_text("utf-8")
    assert all(route.vehicle_id in html for route in solution.routes)

    _ok("instruct", str(json_path), "--inst", SP40, "--frota", FROTA, "--provedor", "mock")
    instrucoes = (tmp_path / "sp_40_ga_vrp_s7_instrucoes.md").read_text("utf-8")
    assert instrucoes.startswith("# Instruções de entrega — sp_40")
    assert all(route.vehicle_id in instrucoes for route in solution.routes)

    _ok(
        "report", str(json_path), "--inst", SP40, "--frota", FROTA,
        "--periodo", "semanal", "--provedor", "mock",
    )  # fmt: skip
    assert (tmp_path / "sp_40_ga_vrp_s7_relatorio_semanal.md").read_text("utf-8").strip()

    saida = _ok(
        "ask", str(json_path), "Qual veículo chega mais tarde?",
        "--inst", SP40, "--frota", FROTA, "--provedor", "mock",
    )  # fmt: skip
    assert "LLM: mock/mock" in saida
