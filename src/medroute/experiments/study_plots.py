"""Figuras PNG/PDF dos experimentos e mapas esquemáticos."""

from __future__ import annotations

from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

from medroute.domain.models import Priority

from .study import BASELINES, StudyConfig


def _save(fig, path: Path) -> None:
    fig.savefig(path.with_suffix(".png"), dpi=150, bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight", metadata={"CreationDate": None})
    plt.close(fig)


def _aligned_histories(histories: list[list[float]]) -> np.ndarray:
    """Mantém o resultado após a parada até o último passo observado no grupo."""
    longest = max(map(len, histories))
    return np.stack(
        [np.pad(history, (0, longest - len(history)), mode="edge") for history in histories]
    ).astype(float)


def render_figures(
    config: StudyConfig, solutions: dict, design: list[dict], summaries: list[dict]
) -> None:
    config.figures.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    instances = list(dict.fromkeys(row["instance_nome"] for row in design))
    colors = plt.get_cmap("tab10").colors
    labels = {
        "nearest_neighbor": "NN",
        "nearest_neighbor_two_opt": "NN + 2-opt",
        "savings": "Savings",
        "random": "Aleatório",
        "puro": "GA puro",
        "hibrido": "GA híbrido",
        "two_opt_local": "2-opt local",
    }
    for exp, experiment in config.experiments.items():
        variants = list(experiment.variants) + (list(BASELINES) if experiment.baselines else [])
        fig, axes = plt.subplots(2, len(instances), figsize=(5 * len(instances), 8), squeeze=False)
        for column, instance in enumerate(instances):
            upper, lower = axes[:, column]
            for i, variant in enumerate(variants):
                s = next(
                    row
                    for row in summaries
                    if (row["experiment"], row["instance_nome"], row["configuration"])
                    == (exp, instance, variant)
                )
                upper.bar(
                    i,
                    s["fitness_comum_media"],
                    yerr=s["fitness_comum_dp"],
                    capsize=4,
                    color=colors[i % len(colors)],
                    alpha=0.85,
                )
                runs = [
                    solutions[d["job_id"]]
                    for d in design
                    if (d["experiment"], d["instance_nome"], d["configuration"])
                    == (exp, instance, variant)
                ]
                if variant in BASELINES:
                    lower.axhline(
                        mean(r["fitness"] for r in runs),
                        color=colors[i],
                        linestyle="--",
                        label=labels.get(variant, variant),
                    )
                    continue
                histories = _aligned_histories([r["historico_fitness"] for r in runs])
                if exp == "E5":
                    histories = 100 * histories / histories[:, :1]
                avg = histories.mean(axis=0)
                sd = histories.std(axis=0, ddof=1) if len(histories) > 1 else np.zeros_like(avg)
                lower.plot(avg, color=colors[i], label=labels.get(variant, variant))
                lower.fill_between(
                    np.arange(len(avg)), avg - sd, avg + sd, color=colors[i], alpha=0.12
                )
            upper.set(
                title=instance,
                ylabel="Fitness com pesos oficiais (R$)",
                xticks=range(len(variants)),
                xticklabels=[labels.get(v, v) for v in variants],
            )
            upper.tick_params(axis="x", rotation=35)
            lower.set(
                xlabel="Geração (0 = população inicial)",
                ylabel=(
                    "% do fitness inicial de cada perfil" if exp == "E5" else "Melhor fitness (R$)"
                ),
            )
            if exp == "E6":
                upper.set_yscale("log")
                lower.set_yscale("log")
                upper.set_ylabel("Fitness com pesos oficiais (R$; escala log)")
                lower.set_ylabel("Melhor fitness (R$; escala log)")
            for ax in (upper, lower):
                ax.grid(axis="y", alpha=0.2)
            lower.legend(fontsize=7)
        fig.suptitle(
            f"{exp} · {experiment.title}\nMédia ± desvio amostral · {len(config.seeds)} seeds"
        )
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        _save(fig, config.figures / exp.lower())

    if "E5" in config.experiments:
        fig, axes = plt.subplots(1, len(instances), figsize=(5 * len(instances), 4), squeeze=False)
        for ax, instance in zip(axes[0], instances, strict=True):
            for i, variant in enumerate(config.experiments["E5"].variants):
                s = next(
                    row
                    for row in summaries
                    if (row["experiment"], row["instance_nome"], row["configuration"])
                    == ("E5", instance, variant)
                )
                ax.errorbar(
                    s["custo_operacional_media"],
                    s["prioridade_comum_media"],
                    xerr=s["custo_operacional_dp"],
                    yerr=s["prioridade_comum_dp"],
                    marker="o",
                    capsize=4,
                    color=colors[i],
                    label=variant,
                )
            ax.set(
                title=instance,
                xlabel="Custo operacional (R$)",
                ylabel="Custo de prioridade com pesos oficiais (R$)",
            )
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
        fig.suptitle("E5 · Custo de operação e tempo até a chegada\nMédia ± desvio amostral")
        fig.tight_layout(rect=(0, 0, 1, 0.9))
        _save(fig, config.figures / "e5_componentes")

    # Coordenadas são geográficas; os segmentos não representam trajetos viários.
    for instance in instances:
        candidates = [
            d
            for d in design
            if d["experiment"] == "E6"
            and d["configuration"] == "hibrido"
            and d["instance_nome"] == instance
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda d: solutions[d["job_id"]]["fitness"])
        solution = solutions[best["job_id"]]
        inst_path = next(p for p in config.instances if p.stem == instance)
        from medroute.data import load_instance

        inst = load_instance(inst_path)
        points = {d.id: (d.lon, d.lat) for d in inst.deliveries}
        depot = (inst.depot.lon, inst.depot.lat)
        fig, ax = plt.subplots(figsize=(8, 6))
        for i, route in enumerate(solution["routes"]):
            coords = [depot, *[points[stop] for stop in route["sequence"]], depot]
            ax.plot(
                *zip(*coords, strict=True),
                color=colors[i],
                linewidth=1,
                marker=".",
                label=route["vehicle_id"],
                alpha=0.8,
            )
        critical = [points[d.id] for d in inst.deliveries if d.prioridade == Priority.CRITICA]
        if critical:
            ax.scatter(
                *zip(*critical, strict=True), marker="s", color="black", s=28, label="Crítica"
            )
        ax.scatter(
            *depot, marker="*", s=180, color="gold", edgecolors="black", zorder=5, label="Depósito"
        )
        ax.set(
            xlabel="Longitude",
            ylabel="Latitude",
            title=(
                f"{instance} · melhor GA híbrido · seed {best['seed']}\n"
                "Traçado esquemático entre coordenadas; distância haversine × 1,30"
            ),
        )
        ax.set_aspect(1 / np.cos(np.radians(inst.depot.lat)))
        ax.xaxis.set_major_locator(MaxNLocator(5))
        ax.legend(fontsize=8)
        fig.tight_layout()
        _save(fig, config.figures / f"rotas_{instance}")
