"""Métricas descritivas, sem alterar as soluções nem misturar unidades de violação."""

from collections import defaultdict
from collections.abc import Sequence
from statistics import mean, stdev

from medroute.domain.models import Solution

MetricRow = dict[str, str | int | float | None]


def extract_metrics(solution: Solution) -> MetricRow:
    """Durações são as informadas pelo decoder; total e máximo têm sentidos distintos."""
    used_routes = [route for route in solution.routes if route.sequence]
    violated = sum(any(value > 0 for value in route.violacoes.values()) for route in used_routes)
    return {
        "instance_nome": solution.instance_nome,
        "algoritmo": solution.algoritmo,
        "seed": solution.seed,
        "fitness": solution.fitness,
        "custo_operacional": solution.custo_operacional,
        "distancia_total_km": solution.distancia_total_km,
        "duracao_total_min": sum(route.duracao_min for route in used_routes),
        "duracao_max_min": max((route.duracao_min for route in used_routes), default=0.0),
        "veiculos_utilizados": len(used_routes),
        "entregas_atendidas": sum(len(route.sequence) for route in used_routes),
        "rotas_com_violacao": violated,
        "percentual_rotas_com_violacao": (
            100.0 * violated / len(used_routes) if used_routes else 0.0
        ),
        "penalidade_total": sum(solution.penalidades.values()),
        "tempo_exec_s": solution.tempo_exec_s,
    }


def improvement_pct(value: float, reference: float) -> float | None:
    """Redução relativa para métricas a minimizar; referência zero é indefinida."""
    return 100.0 * (reference - value) / reference if reference != 0 else None


def compare_solutions(solutions: Sequence[Solution], reference: Solution) -> list[MetricRow]:
    """Adiciona reduções de fitness/custo/km; positivo significa melhoria."""
    rows: list[MetricRow] = []
    for solution in solutions:
        if solution.instance_nome != reference.instance_nome:
            raise ValueError("a comparação exige soluções da mesma instância")
        row = extract_metrics(solution)
        row["referencia"] = reference.algoritmo
        for metric in ("fitness", "custo_operacional", "distancia_total_km"):
            row[f"{metric}_melhoria_pct"] = improvement_pct(
                getattr(solution, metric), getattr(reference, metric)
            )
        rows.append(row)
    return rows


def summarize_solutions(solutions: Sequence[Solution]) -> list[MetricRow]:
    """Agrupa por instância/algoritmo: média, desvio amostral e mínimo de cada métrica."""
    groups: dict[tuple[str, str], list[Solution]] = defaultdict(list)
    for solution in solutions:
        groups[solution.instance_nome, solution.algoritmo].append(solution)
    summaries: list[MetricRow] = []
    for (instance_name, algorithm), runs in sorted(groups.items()):
        rows = [extract_metrics(run) for run in runs]
        summary: MetricRow = {
            "instance_nome": instance_name,
            "algoritmo": algorithm,
            "execucoes": len(runs),
        }
        for metric in sorted(rows[0].keys() - {"instance_nome", "algoritmo", "seed"}):
            values = [row[metric] for row in rows]
            summary[f"{metric}_media"] = mean(values)
            summary[f"{metric}_dp"] = stdev(values) if len(values) > 1 else 0.0
            summary[f"{metric}_min"] = min(values)
        summary["percentual_execucoes_com_violacao"] = (
            100.0 * sum(row["rotas_com_violacao"] > 0 for row in rows) / len(rows)
        )
        summaries.append(summary)
    return summaries
