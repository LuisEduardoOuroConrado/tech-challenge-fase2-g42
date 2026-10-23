import copy
import math

import pytest

from medroute.experiments.study import _execute, _hash, build_design, load_study_config, run_study
from medroute.experiments.study_analysis import _resolve_jobs, analysis_rows, summarize_rows


def test_reanalise_portavel_confere_conteudo_sem_exigir_caminhos_do_host_original(small_study):
    solutions, design, metadata = run_study(small_study, progress=lambda _: None)
    migrated_solutions, migrated_jobs, ids = {}, {}, {}
    for job_id, recipe in metadata["jobs"].items():
        recipe = copy.deepcopy(recipe)
        old_inputs = recipe["inputs"]
        recipe["inputs"] = {}
        for field in ("instance", "fleet", "fitness"):
            old_path = recipe[field]
            recipe[field] = "/outro-host/" + field
            recipe["inputs"][recipe[field]] = old_inputs[old_path]
        recipe["python"] = "3.11.99"
        new_id = _hash(recipe)
        ids[job_id] = new_id
        migrated_jobs[new_id] = recipe
        migrated_solutions[new_id] = solutions[job_id]
    migrated_design = [{**entry, "job_id": ids[entry["job_id"]]} for entry in reversed(design)]
    migrated_metadata = {**metadata, "jobs": migrated_jobs}
    resolved = _resolve_jobs(small_study, migrated_solutions, migrated_design, migrated_metadata)
    rows = analysis_rows(small_study, migrated_solutions, migrated_design, resolved)
    assert len(rows) == len(design)
    migrated_jobs[next(iter(migrated_jobs))]["sources"] = {"adulterado": "hash"}
    with pytest.raises(ValueError, match="diferem"):
        _resolve_jobs(small_study, migrated_solutions, migrated_design, migrated_metadata)


def test_audita_contagem_por_atributo_da_base_em_random_sp80():
    config = load_study_config()
    jobs, design = build_design(config)
    entry = next(
        d
        for d in design
        if (d["experiment"], d["configuration"], d["instance_nome"], d["seed"])
        == ("E6", "random", "sp_80", 7)
    )
    data = _execute(jobs[entry["job_id"]])
    row = analysis_rows(config, {entry["job_id"]: data}, [entry], jobs)[0]
    assert row["incompatibilidades_duplicadas"] > 0
    assert row["fitness_sem_duplicacao"] < row["fitness_comum"]
    assert row["violacao_hard"] == 1


def test_e5_usa_objetivo_comum_e_estatistica_amostral_pareada(small_study):
    solutions, design, metadata = run_study(small_study, progress=lambda _: None)
    rows = analysis_rows(small_study, solutions, design, metadata["jobs"])
    cost = next(r for r in rows if r["configuration"] == "custo")
    assert cost["prioridade_objetivo"] == 0 < cost["prioridade_comum"]
    assert cost["fitness_comum"] > cost["fitness"]
    summaries, _ = summarize_rows(small_study, rows)
    assert all("criticas_atrasadas_media" in row for row in summaries)
    synthetic = [dict(rows[0], seed=7, fitness_comum=10), dict(rows[0], seed=17, fitness_comum=20)]
    summary, pairs = summarize_rows(small_study, synthetic)
    assert summary[0]["fitness_comum_media"] == 15
    assert summary[0]["fitness_comum_dp"] == pytest.approx(math.sqrt(50))
    assert summary[0]["empate"] == 2 and all(p["resultado"] == "empate" for p in pairs)
