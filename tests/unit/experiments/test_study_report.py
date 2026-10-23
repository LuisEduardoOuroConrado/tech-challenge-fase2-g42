import csv
import gzip
import json

import pytest

from medroute.experiments.study import main, run_study
from medroute.experiments.study_report import write_study_report


def test_exportacao_inclui_figuras_tabelas_validacao_e_cli_render_only(small_study, tmp_path):
    solutions, design, metadata = run_study(small_study, workers=2, progress=lambda _: None)
    write_study_report(small_study, solutions, design, metadata)
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
