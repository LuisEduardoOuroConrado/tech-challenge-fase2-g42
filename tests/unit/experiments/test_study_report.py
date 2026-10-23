import csv
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from medroute.experiments.study import Experiment, Variant, main, run_study
from medroute.experiments.study_report import write_study_report


def test_exportacao_inclui_figuras_tabelas_validacao_e_cli_render_only(small_study, tmp_path):
    solutions, design, metadata = run_study(small_study, workers=2, progress=lambda _: None)
    write_study_report(small_study, solutions, design, metadata)
    exported_metadata = json.loads((small_study.out / "metadata.json").read_text())
    from medroute.experiments import study

    assert exported_metadata["analysis"]["source_sha256"]["study.py"] == hashlib.sha256(
        Path(study.__file__).read_bytes()
    ).hexdigest()
    assert exported_metadata["execution_provenance"] == metadata["execution_provenance"]
    for path in small_study.out.glob("*.csv"):
        # .gitattributes normaliza textos para LF; o hash deve sobreviver ao commit.
        assert b"\r\n" not in path.read_bytes()
    validation = json.loads((small_study.out / "validacao.json").read_text())
    assert validation["unique_solutions_validated"] == 12
    assert validation["observations"] == 14
    assert len(list(small_study.figures.glob("*.png"))) == 4
    assert len(list(small_study.figures.glob("*.pdf"))) == 4
    import yaml

    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(small_study.model_dump(mode="json")))
    main(["--config", str(path), "--render-only"])
    assert (small_study.out / "paired.csv").is_file()
    for exp in small_study.experiments:
        with gzip.open(small_study.out / "convergence" / f"{exp}.csv.gz", "rt") as stream:
            points = list(csv.DictReader(stream))
        assert len(points) == sum(
            len(solutions[d["job_id"]]["historico_fitness"])
            for d in design
            if d["experiment"] == exp
        )
    from typer.testing import CliRunner

    from medroute.app.cli import app

    result = CliRunner().invoke(
        app,
        [
            "report",
            str(small_study.out / "e6_solutions.json"),
            "--inst",
            str(small_study.instances[0]),
            "--frota",
            str(small_study.fleet),
            "--periodo",
            "semanal",
            "--provedor",
            "mock",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (small_study.out / "e6_solutions_relatorio_semanal.md").is_file()
    with pytest.raises(SystemExit):
        main(["--config", str(path), "--workers", "0"])


def test_exporta_e_reanalisa_seeds_com_parada_antecipada(small_study, tmp_path):
    import yaml

    config = small_study.model_copy(
        update={
            "seeds": [7, 17, 42, 73, 101],
            "base_ga": small_study.base_ga.model_copy(
                update={
                    "population_size": 10,
                    "generations": 40,
                    "patience": 5,
                    "mutation_rate": 0.2,
                    "seed_nearest_neighbor": False,
                    "local_search_rate": 0,
                }
            ),
            "experiments": {"E1": Experiment(title="Parada", variants={"ga": Variant()})},
        }
    )
    solutions, design, metadata = run_study(config, progress=lambda _: None)
    lengths = [len(s["historico_fitness"]) for s in solutions.values()]
    assert len(set(lengths)) > 1
    assert max(lengths) < config.base_ga.generations
    write_study_report(config, solutions, design, metadata)
    path = tmp_path / "patience.yaml"
    path.write_text(yaml.safe_dump(config.model_dump(mode="json")))
    main(["--config", str(path), "--render-only"])
    assert (config.figures / "e1.png").is_file()
    assert (config.figures / "e1.pdf").is_file()
    with gzip.open(config.out / "convergence/E1.csv.gz", "rt") as stream:
        assert len(list(csv.DictReader(stream))) == sum(lengths)


def test_ga_sem_elitismo_executa_retoma_e_exporta_historico_original(small_study, monkeypatch):
    config = small_study.model_copy(
        update={
            "seeds": [7, 17, 42],
            "base_ga": small_study.base_ga.model_copy(
                update={
                    "population_size": 10,
                    "generations": 40,
                    "mutation_rate": 0.2,
                    "seed_nearest_neighbor": False,
                    "local_search_rate": 0,
                }
            ),
            "experiments": {
                "E1": Experiment(title="Sem elitismo", variants={"ga": Variant(ga={"elitism": 0})})
            },
        }
    )
    solutions, design, metadata = run_study(config, progress=lambda _: None)
    assert any(
        b > a + 1e-7
        for s in solutions.values()
        for a, b in zip(s["historico_fitness"], s["historico_fitness"][1:], strict=False)
    )
    assert any(s["historico_fitness"][-1] > s["fitness"] + 1e-7 for s in solutions.values())
    monkeypatch.setattr(
        "medroute.experiments.study._execute", lambda _: pytest.fail("cache ignorado")
    )
    resumed, _, _ = run_study(config, progress=lambda _: None)
    assert resumed == solutions
    write_study_report(config, resumed, design, metadata)
    with gzip.open(config.out / "convergence/E1.csv.gz", "rt") as stream:
        points = list(csv.DictReader(stream))
    for job_id, solution in solutions.items():
        exported = [float(row["fitness"]) for row in points if row["job_id"] == job_id]
        assert exported == solution["historico_fitness"]
    assert (config.figures / "e1.png").is_file()


def test_mapa_usa_nome_interno_ao_exportar_e_reanalisar_arquivo_renomeado(small_study, tmp_path):
    import yaml

    renamed = tmp_path / "instancia_renomeada.json"
    renamed.write_bytes(small_study.instances[0].read_bytes())
    config = small_study.model_copy(
        update={
            "instances": [renamed],
            "seeds": [7],
            "experiments": {"E6": Experiment(title="Rotas", variants={"hibrido": Variant()})},
        }
    )
    solutions, design, metadata = run_study(config, progress=lambda _: None)
    assert {s["instance_nome"] for s in solutions.values()} == {"sp_15"}
    write_study_report(config, solutions, design, metadata)
    path = tmp_path / "renamed.yaml"
    path.write_text(yaml.safe_dump(config.model_dump(mode="json")))
    main(["--config", str(path), "--render-only"])
    assert (config.figures / "rotas_sp_15.png").is_file()
    assert (config.figures / "rotas_sp_15.pdf").is_file()
