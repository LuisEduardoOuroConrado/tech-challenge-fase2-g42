import csv
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from medroute.domain.models import Solution
from medroute.experiments.runner import (
    ExperimentConfig,
    load_experiment_config,
    main,
    run_experiment,
    write_results,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def config(tmp_path):
    return ExperimentConfig(
        name="teste",
        instances=[ROOT / "data/instances/sp_15.json"],
        fleet=ROOT / "configs/frota.yaml",
        fitness=ROOT / "configs/fitness.yaml",
        seeds=[7, 17],
        out=tmp_path / "results",
        ga_configs={
            name: dict(
                population_size=4,
                generations=2,
                crossover_rate=0.9,
                mutation_rate=0.2,
                elitism=1,
                tournament_size=2,
                crossover="ox",
                mutation="inversion",
                seed_nearest_neighbor=hybrid,
            )
            for name, hybrid in [("puro", False), ("hibrido", True)]
        },
    )


def test_matriz_de_execucoes_separa_configs_e_pareia_referencia_por_seed(config):
    original = config.model_dump_json()
    messages = []
    result = run_experiment(config, progress=messages.append)
    assert len(result.solutions) == len(result.metrics) == 12
    assert len(result.summary) == 6
    assert len(messages) == 2
    assert {row["algoritmo"] for row in result.summary} >= {"ga_puro", "ga_hibrido", "savings"}
    assert all(row["execucoes"] == 2 for row in result.summary)
    for row in result.metrics:
        reference = next(
            solution
            for solution in result.solutions
            if solution.seed == row["seed"] and solution.algoritmo == "nearest_neighbor"
        )
        assert row["fitness_melhoria_pct"] == pytest.approx(
            100 * (reference.fitness - row["fitness"]) / reference.fitness
        )
    assert config.model_dump_json() == original


def test_reproduz_solucoes_exceto_tempo_e_snapshot_identifica_entradas(config):
    first, second = run_experiment(config), run_experiment(config)
    assert [s.model_dump(exclude={"tempo_exec_s"}) for s in first.solutions] == [
        s.model_dump(exclude={"tempo_exec_s"}) for s in second.solutions
    ]
    assert first.metadata["sha256_source"] == second.metadata["sha256_source"]
    assert first.metadata["sha256_inputs"] == second.metadata["sha256_inputs"]
    assert len(first.metadata["sha256_inputs"]) == 3
    assert first.metadata["instances"][0]["nome"] == "sp_15"
    assert "jornada" in first.metadata["fitness_config"]["penalidades"]


def test_exporta_json_validos_csv_e_convergencia_por_configuracao(config):
    result = run_experiment(config)
    out = write_results(result, config.out)
    assert {path.name for path in out.iterdir()} == {
        "solutions.json",
        "metadata.json",
        "metrics.csv",
        "summary.csv",
        "convergence.csv",
    }
    solutions = [
        Solution.model_validate(value)
        for value in json.loads((out / "solutions.json").read_text(encoding="utf-8"))
    ]
    assert solutions == result.solutions
    with (out / "metrics.csv").open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 12
    with (out / "convergence.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == sum(len(solution.historico_fitness) for solution in solutions)
    assert {row["algoritmo"] for row in rows} >= {"ga_puro", "ga_hibrido"}
    assert json.loads((out / "metadata.json").read_text())["experiment"]["seeds"] == [7, 17]


@pytest.mark.parametrize(
    "updates",
    [
        {"seeds": []},
        {"seeds": [7, 7]},
        {"instances": []},
        {"ga_configs": {}},
        {"vehicles": []},
        {"vehicles": ["van-01", "van-01"]},
        {"two_opt_max_passes": 0},
    ],
)
def test_rejeita_matriz_de_execucoes_invalida(config, updates):
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({**config.model_dump(), **updates})


def test_loader_resolve_caminhos_pelo_yaml_independente_do_cwd(config, tmp_path, monkeypatch):
    path = tmp_path / "experiment.yaml"
    data = config.model_dump(mode="json")
    data["out"] = "relative/results"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.chdir(ROOT)
    assert load_experiment_config(path).out == tmp_path / "relative/results"


def test_loader_rejeita_erro_yaml_e_campo_desconhecido(config, tmp_path):
    path = tmp_path / "bad.yaml"
    for content in ("[", yaml.safe_dump({**config.model_dump(mode="json"), "typo": 1})):
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match="configuração de experimento inválida"):
            load_experiment_config(path)


def test_veiculo_desconhecido_e_instancias_com_nome_repetido_falham_antes_de_exportar(config):
    with pytest.raises(ValueError, match="veículos desconhecidos"):
        run_experiment(config.model_copy(update={"vehicles": ["aviao"]}))
    with pytest.raises(ValueError, match="nomes distintos"):
        run_experiment(config.model_copy(update={"instances": config.instances * 2}))
    assert not config.out.exists()


def test_filtro_tsp_seleciona_mesmo_veiculo_para_todos(config):
    result = run_experiment(config.model_copy(update={"vehicles": ["van-01"], "seeds": [7]}))
    assert all([route.vehicle_id for route in s.routes] == ["van-01"] for s in result.solutions)
    assert [v["id"] for v in result.metadata["instances"][0]["fleet"]] == ["van-01"]


def test_cli_usa_yaml_e_overrides_e_rejeita_seed_repetida(config, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config.model_dump(mode="json")), encoding="utf-8")
    out = tmp_path / "override"
    main(["--config", str(path), "--out", str(out), "--seeds", "42"])
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["experiment"]["seeds"] == [42]
    assert len(json.loads((out / "solutions.json").read_text())) == 6
    with pytest.raises(SystemExit) as error:
        main(["--config", str(path), "--seeds", "7", "7"])
    assert error.value.code == 2
