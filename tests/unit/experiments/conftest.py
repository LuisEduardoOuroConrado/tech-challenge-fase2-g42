import pytest

from medroute.experiments.study import Experiment, StudyConfig, Variant, load_study_config


@pytest.fixture
def small_study(tmp_path):
    config = load_study_config()
    return StudyConfig.model_validate(
        {
            **config.model_dump(),
            "instances": config.instances[:1],
            "seeds": [7, 17],
            "out": tmp_path / "results",
            "cache": tmp_path / "cache",
            "figures": tmp_path / "figures",
            "base_ga": {**config.base_ga.model_dump(), "population_size": 4, "generations": 2},
            "experiments": {
                "E5": Experiment(
                    title="Pesos",
                    reference="equilibrado",
                    variants={"equilibrado": Variant(), "custo": Variant(priority_scale=0)},
                ),
                "E6": Experiment(
                    title="Comparativo",
                    baselines=True,
                    reference="nearest_neighbor_two_opt",
                    variants={"hibrido": Variant()},
                ),
            },
        }
    )
