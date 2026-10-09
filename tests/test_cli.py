import json
from pathlib import Path

from typer.testing import CliRunner

from medroute.app.cli import app
from medroute.domain.models import Solution

ROOT = Path(__file__).resolve().parents[1]
FROTA = str(ROOT / "configs" / "frota.yaml")
SP15 = str(ROOT / "data" / "instances" / "sp_15.json")

runner = CliRunner()


def test_demo_confirma_instalacao() -> None:
    result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0
    assert "medroute instalado e pronto para uso." in result.stdout


def test_gen_cria_instancias_reproduziveis(tmp_path: Path) -> None:
    result = runner.invoke(app, ["gen", "--out", str(tmp_path), "--frota", FROTA])

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sp_15.json", "sp_40.json", "sp_80.json"]
    assert (tmp_path / "sp_15.json").read_text("utf-8") == Path(SP15).read_text("utf-8")


def solve(tmp_path: Path, *extra: str):
    args = ["solve", "--inst", SP15, "--frota", FROTA, "--geracoes", "10", "--populacao", "20"]
    return runner.invoke(app, [*args, "--out-dir", str(tmp_path), *extra])


def test_solve_tsp_gera_json_e_mapa(tmp_path: Path) -> None:
    result = solve(tmp_path, "--veiculo", "van-01", "--seed", "3")

    assert result.exit_code == 0, result.output
    solution = Solution.model_validate_json((tmp_path / "sp_15_ga_tsp_s3.json").read_text("utf-8"))
    assert [route.vehicle_id for route in solution.routes] == ["van-01"]
    assert len(solution.routes[0].sequence) == 15
    assert len(solution.historico_fitness) == 10
    assert (tmp_path / "sp_15_ga_tsp_s3.html").exists()


def test_solve_vrp_sem_mapa(tmp_path: Path) -> None:
    result = solve(tmp_path, "--no-mapa")

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sp_15_ga_vrp_s42.json"]


def test_solve_rejeita_veiculo_inexistente_e_config_invalida(tmp_path: Path) -> None:
    assert solve(tmp_path, "--veiculo", "aviao-01").exit_code == 1
    assert solve(tmp_path, "--crossover", "cx").exit_code == 1
    assert list(tmp_path.iterdir()) == []


def test_solve_instancia_inexistente(tmp_path: Path) -> None:
    result = runner.invoke(app, ["solve", "--inst", str(tmp_path / "nao.json"), "--frota", FROTA])
    assert result.exit_code == 1


def test_map_a_partir_de_solution_salva(tmp_path: Path) -> None:
    fixture = ROOT / "tests" / "fixtures" / "solution_sp15.json"
    solution_path = tmp_path / "sol.json"
    solution_path.write_text(fixture.read_text("utf-8"), encoding="utf-8")

    result = runner.invoke(app, ["map", str(solution_path), "--inst", SP15, "--frota", FROTA])

    assert result.exit_code == 0, result.output
    html = (tmp_path / "sol.html").read_text("utf-8")
    assert all(route["vehicle_id"] in html for route in json.loads(fixture.read_text())["routes"])


def test_instruct_gera_markdown_com_mock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isola de um .env local
    fixture = ROOT / "tests" / "fixtures" / "solution_sp15.json"
    solution_path = tmp_path / "sol.json"
    solution_path.write_text(fixture.read_text("utf-8"), encoding="utf-8")

    result = runner.invoke(
        app,
        ["instruct", str(solution_path), "--inst", SP15, "--frota", FROTA, "--provedor", "mock"],
    )

    assert result.exit_code == 0, result.output
    md = (tmp_path / "sol_instrucoes.md").read_text("utf-8")
    assert md.startswith("# Instruções de entrega")
    usadas = [r["vehicle_id"] for r in json.loads(fixture.read_text())["routes"] if r["sequence"]]
    assert all(vid in md for vid in usadas)


def test_instruct_rejeita_provedor_invalido(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = ROOT / "tests" / "fixtures" / "solution_sp15.json"
    args = ["instruct", str(fixture), "--inst", SP15, "--frota", FROTA, "--provedor", "x"]
    result = runner.invoke(app, [*args, "--out", str(tmp_path / "i.md")])

    assert result.exit_code == 1
    assert not (tmp_path / "i.md").exists()
