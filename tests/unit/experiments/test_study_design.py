import pytest
from pydantic import ValidationError

from medroute.experiments.study import StudyConfig, build_design, load_study_config


def test_design_oficial_completo_isola_fatores_e_reutiliza_referencia():
    config = load_study_config()
    jobs, design = build_design(config)
    assert len(jobs) == 240
    assert len(design) == 300
    assert set(config.experiments) == {f"E{i}" for i in range(1, 7)}
    assert config.seeds == [7, 17, 42, 73, 101]
    assert {p.stem for p in config.instances} == {"sp_15", "sp_40", "sp_80"}
    assert config.base_ga.generations == 300 and config.base_ga.patience is None
    for exp, key, values in (
        ("E1", "population_size", {50, 100, 200}),
        ("E2", "mutation_rate", {0.01, 0.05, 0.15}),
        ("E3", "crossover", {"ox", "pmx"}),
    ):
        configs = [jobs[d["job_id"]]["ga"] for d in design if d["experiment"] == exp]
        assert {c[key] for c in configs} == values
        for c in configs:
            assert {k: v for k, v in c.items() if k != key} == {
                k: v for k, v in config.base_ga.model_dump().items() if k != key
            }
    assert {jobs[d["job_id"]]["priority_scale"] for d in design if d["experiment"] == "E5"} == {
        0,
        1,
        3,
    }
    reference_ids = [
        d["job_id"]
        for d in design
        if d["configuration"] in ("pop_100", "taxa_005", "ox", "equilibrado", "hibrido")
    ]
    assert len(reference_ids) == 75 and len(set(reference_ids)) == 15


@pytest.mark.parametrize(
    "updates",
    [
        {"seeds": []},
        {"seeds": [7, 7]},
        {"instances": []},
        {"experiments": {}},
        {"experiments": {"E1": {"title": "x", "variants": {"x": {"ga": {"typo": 1}}}}}},
        {"experiments": {"E1": {"title": "x", "reference": "ausente", "variants": {"x": {}}}}},
    ],
)
def test_rejeita_design_invalido(small_study, updates):
    with pytest.raises(ValidationError):
        StudyConfig.model_validate({**small_study.model_dump(), **updates})
