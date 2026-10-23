import copy
import json

import pytest

from medroute.domain.models import Solution
from medroute.experiments.study import _context, build_design, run_study, validate_solution


def test_reproducao_retomada_hashes_e_cache_adulterado(small_study, monkeypatch):
    first, design, metadata = run_study(small_study, progress=lambda _: None)
    assert len(first) == 12 and len(design) == 14
    monkeypatch.setattr(
        "medroute.experiments.study._execute", lambda _: pytest.fail("cache ignorado")
    )
    second, _, _ = run_study(small_study, progress=lambda _: None)
    assert first == second
    modified = small_study.model_copy(update={"seeds": [42]})
    assert set(build_design(modified)[0]).isdisjoint(metadata["jobs"])
    monkeypatch.setattr("medroute.experiments.study.source_hashes", lambda: {"changed.py": "new"})
    assert set(build_design(small_study)[0]).isdisjoint(metadata["jobs"])
    monkeypatch.undo()
    path = next(small_study.cache.glob("*.json"))
    record = json.loads(path.read_text())
    record["solution"]["fitness"] += 1
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="cache corrompido"):
        run_study(small_study, progress=lambda _: None)


def test_recalcula_cobertura_rotas_fitness_e_violacoes(small_study):
    solutions, _, metadata = run_study(small_study, progress=lambda _: None)
    job_id = next(iter(solutions))
    original = solutions[job_id]
    inst, dm, fn = _context(metadata["jobs"][job_id])
    for mutate in (
        lambda s: s.update(fitness=s["fitness"] + 1),
        lambda s: s["routes"][0].update(distancia_km=0),
        lambda s: s["routes"][0]["sequence"].pop(),
        lambda s: s["routes"][0]["violacoes"].update(deadline=99),
    ):
        corrupt = copy.deepcopy(original)
        mutate(corrupt)
        with pytest.raises(ValueError):
            validate_solution(Solution.model_validate(corrupt), inst, dm, fn)
