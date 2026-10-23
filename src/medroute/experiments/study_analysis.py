"""Métricas, estatística pareada e conferência portável da proveniência."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean, stdev

from medroute.constraints import cronograma_rota, violacao_compatibilidade
from medroute.domain.models import Priority, Solution
from medroute.experiments.metrics import extract_metrics, improvement_pct
from medroute.ga import load_fitness_config, make_fitness

from .study import StudyConfig, _context, _hash, build_design, validate_solution


def analysis_rows(
    config: StudyConfig, solutions: dict, design: list[dict], jobs: dict
) -> list[dict]:
    rows, evaluated = [], {}
    for entry in design:
        job_id = entry["job_id"]
        if job_id not in evaluated:
            recipe = jobs[job_id]
            solution = Solution.model_validate(solutions[job_id])
            if solution.seed != recipe["seed"] or solution.algoritmo != recipe["algorithm"]:
                raise ValueError("identidade da execução divergente")
            inst, dm, fn = _context(recipe)
            validate_solution(solution, inst, dm, fn)
            common = make_fitness(inst, dm, fn.fleet, load_fitness_config(config.fitness))
            vehicles = {v.id: v for v in inst.fleet}
            arrivals = {}
            unique_incompatible = duplicates = 0
            audited_routes = []
            for route in solution.routes:
                arrivals.update(
                    cronograma_rota(
                        dm,
                        vehicles[route.vehicle_id],
                        route.sequence,
                        inst,
                        fn.fleet,
                        fn.fleet.saida_min,
                    )
                )
                cargo = [d for d in inst.deliveries if d.id in route.sequence]
                count = violacao_compatibilidade(fn.fleet, vehicles[route.vehicle_id], cargo)
                unique_incompatible += count
                duplicates += route.violacoes["compatibilidade"] - count
                audited_routes.append(
                    route.model_copy(
                        update={"violacoes": {**route.violacoes, "compatibilidade": count}}
                    )
                )
            critical = [d for d in inst.deliveries if d.prioridade == Priority.CRITICA]
            row = extract_metrics(solution)
            row.update(
                {
                    "fitness_comum": common(solution.routes),
                    "fitness_sem_duplicacao": common(audited_routes),
                    "incompatibilidades_entregas": unique_incompatible,
                    "incompatibilidades_duplicadas": duplicates,
                    "prioridade_comum": common.priority_cost(solution.routes),
                    "prioridade_objetivo": fn.priority_cost(solution.routes),
                    "chegada_critica_media_min": mean(arrivals[d.id] for d in critical)
                    if critical
                    else 0,
                    "criticas_atrasadas": int(
                        sum(arrivals[d.id] > d.deadline_min + 1e-7 for d in critical)
                    ),
                    "deadline_atraso_min": sum(r.violacoes["deadline"] for r in solution.routes),
                    "jornada_excesso_min": sum(r.violacoes["jornada"] for r in solution.routes),
                    "violacao_hard": int(
                        any(
                            r.violacoes[k] > 1e-7
                            for r in solution.routes
                            for k in ("capacidade", "autonomia", "compatibilidade")
                        )
                    ),
                }
            )
            evaluated[job_id] = row
        row = evaluated[job_id]
        if row["instance_nome"] != entry["instance_nome"] or row["seed"] != entry["seed"]:
            raise ValueError("design não corresponde à execução")
        rows.append({**entry, **row})
    return rows


def summarize_rows(config: StudyConfig, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["experiment"], row["instance_nome"], row["configuration"]].append(row)
    summaries, pairs = [], []
    for (exp, instance, variant), batch in sorted(groups.items()):
        experiment = config.experiments[exp]
        reference = experiment.reference or next(iter(experiment.variants))
        reference_rows = {r["seed"]: r for r in groups[exp, instance, reference]}
        if len({r["seed"] for r in batch}) != len(batch):
            raise ValueError("seed repetida no grupo")
        if set(reference_rows) != {r["seed"] for r in batch}:
            raise ValueError("comparação exige as mesmas seeds")
        summary = {
            "experiment": exp,
            "instance_nome": instance,
            "configuration": variant,
            "n": len(batch),
            "reference": reference,
        }
        for metric, value in batch[0].items():
            if metric in ("seed",) or not isinstance(value, (int, float)):
                continue
            values = [row[metric] for row in batch]
            summary.update(
                {
                    f"{metric}_media": mean(values),
                    f"{metric}_dp": stdev(values) if len(values) > 1 else 0,
                    f"{metric}_min": min(values),
                }
            )
        outcomes = []
        for row in sorted(batch, key=lambda r: r["seed"]):
            ref = reference_rows[row["seed"]]
            delta = ref["fitness_comum"] - row["fitness_comum"]
            outcome = "empate" if abs(delta) <= 1e-7 else ("vitoria" if delta > 0 else "derrota")
            outcomes.append(outcome)
            pairs.append(
                {
                    "experiment": exp,
                    "instance_nome": instance,
                    "configuration": variant,
                    "seed": row["seed"],
                    "reference": reference,
                    "delta_fitness_comum": delta,
                    "resultado": outcome,
                    "melhoria_pct": improvement_pct(row["fitness_comum"], ref["fitness_comum"]),
                }
            )
        for label in ("vitoria", "empate", "derrota"):
            summary[label] = outcomes.count(label)
        ref_mean = mean(row["fitness_comum"] for row in reference_rows.values())
        summary["melhoria_media_pct"] = improvement_pct(summary["fitness_comum_media"], ref_mean)
        summary["execucoes_com_violacao_pct"] = (
            100 * sum(r["rotas_com_violacao"] > 0 for r in batch) / len(batch)
        )
        summary["execucoes_com_violacao_hard_pct"] = (
            100 * sum(r["violacao_hard"] for r in batch) / len(batch)
        )
        summaries.append(summary)
    return summaries, pairs


def _portable_recipe(recipe: dict) -> dict:
    """Caminhos e Python identificam a execução original; a reanálise confere o conteúdo."""
    return {
        **{
            key: value
            for key, value in recipe.items()
            if key not in ("instance", "fleet", "fitness", "inputs", "python")
        },
        "inputs": {
            field: recipe["inputs"][recipe[field]] for field in ("instance", "fleet", "fitness")
        },
    }


def _resolve_jobs(config: StudyConfig, solutions: dict, design: list[dict], metadata: dict) -> dict:
    expected_jobs, expected_design = build_design(config)

    def order(entry):
        return (entry["experiment"], entry["configuration"], entry["instance_nome"], entry["seed"])

    expected = {order(entry): entry for entry in expected_design}
    if (
        len(design) != len(expected)
        or len({order(d) for d in design}) != len(design)
        or {order(d) for d in design} != set(expected)
        or set(solutions) != set(metadata["jobs"])
        or set(solutions) != {entry["job_id"] for entry in design}
    ):
        raise ValueError("design, entradas ou fontes diferem da rodada salva")
    resolved = {}
    for entry in design:
        job_id = entry["job_id"]
        original = metadata["jobs"][job_id]
        current = expected_jobs[expected[order(entry)]["job_id"]]
        if _hash(original) != job_id or _portable_recipe(original) != _portable_recipe(current):
            raise ValueError("design, entradas ou fontes diferem da rodada salva")
        resolved[job_id] = current
    return resolved
