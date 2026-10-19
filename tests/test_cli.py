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


def experiment_yaml(tmp_path: Path) -> Path:
    """Experimento mínimo: sp_15, uma seed, um GA pequeno."""
    path = tmp_path / "exp.yaml"
    ga = {
        "population_size": 6,
        "generations": 2,
        "crossover_rate": 0.9,
        "mutation_rate": 0.2,
        "elitism": 1,
        "tournament_size": 2,
        "crossover": "ox",
        "mutation": "inversion",
    }
    config = {
        "name": "teste",
        "instances": [SP15],
        "fleet": FROTA,
        "fitness": str(ROOT / "configs" / "fitness.yaml"),
        "seeds": [7],
        "ga_configs": {"mini": ga},
        "two_opt_max_passes": 1,
        "out": str(tmp_path / "padrao"),
    }
    path.write_text(json.dumps(config), encoding="utf-8")  # JSON é YAML válido
    return path


def test_compare_roda_o_runner_e_mostra_o_resumo(tmp_path: Path) -> None:
    out = tmp_path / "res"
    args = ["compare", "--config", str(experiment_yaml(tmp_path)), "--seed", "3", "--out", str(out)]
    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert {p.name for p in out.iterdir()} == {
        "solutions.json",
        "metrics.csv",
        "summary.csv",
        "convergence.csv",
        "metadata.json",
    }
    solutions = json.loads((out / "solutions.json").read_text("utf-8"))
    assert {s["seed"] for s in solutions} == {3}  # --seed sobrescreve o YAML
    assert {s["algoritmo"] for s in solutions} >= {"ga_mini", "nearest_neighbor_two_opt"}
    assert "ga_mini" in result.output
    assert not (tmp_path / "padrao").exists()  # --out sobrescreve o YAML


def test_compare_rejeita_yaml_invalido(tmp_path: Path) -> None:
    path = tmp_path / "ruim.yaml"
    path.write_text("name: x\n", encoding="utf-8")
    assert runner.invoke(app, ["compare", "--config", str(path)]).exit_code == 1


def test_report_gera_markdown_com_mock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isola de um .env local
    fixture = ROOT / "tests" / "fixtures" / "solution_sp15.json"
    solution_path = tmp_path / "sol.json"
    solution_path.write_text(fixture.read_text("utf-8"), encoding="utf-8")

    args = ["report", str(solution_path), "--inst", SP15, "--frota", FROTA, "--provedor", "mock"]
    result = runner.invoke(app, [*args, "--periodo", "semanal"])

    assert result.exit_code == 0, result.output
    md = (tmp_path / "sol_relatorio_semanal.md").read_text("utf-8")
    assert md.startswith("# Relatório semanal de entregas")


def test_report_le_lista_e_exige_inst_com_varias_instancias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = json.loads((ROOT / "tests" / "fixtures" / "solution_sp15.json").read_text("utf-8"))
    outra = {**fixture, "instance_nome": "sp_40", "algoritmo": "outro"}
    lista = tmp_path / "solutions.json"
    lista.write_text(json.dumps([fixture, outra]), encoding="utf-8")
    base = ["report", str(lista), "--frota", FROTA, "--provedor", "mock"]

    assert runner.invoke(app, base).exit_code == 1  # duas instâncias, sem --inst
    result = runner.invoke(app, [*base, "--inst", SP15])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "solutions_sp_15_relatorio_diario.md").exists()


def test_report_rejeita_periodo_invalido(tmp_path: Path) -> None:
    fixture = ROOT / "tests" / "fixtures" / "solution_sp15.json"
    result = runner.invoke(app, ["report", str(fixture), "--periodo", "mensal"])
    assert result.exit_code == 1
