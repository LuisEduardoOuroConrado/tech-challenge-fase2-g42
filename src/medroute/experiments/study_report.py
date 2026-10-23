"""Exportação das tabelas, curvas e artefatos auditados de E1–E6."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from .study import ROOT, StudyConfig
from .study_analysis import _resolve_jobs, analysis_rows, summarize_rows
from .study_plots import render_figures


def _csv(path: Path, rows: list[dict]) -> None:
    stream = (
        gzip.open(path, "wt", encoding="utf-8", newline="")
        if path.suffix == ".gz"
        else path.open("w", encoding="utf-8", newline="")
    )
    with stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_study_report(
    config: StudyConfig, solutions: dict, design: list[dict], metadata: dict
) -> None:
    resolved = _resolve_jobs(config, solutions, design, metadata)
    rows = analysis_rows(config, solutions, design, resolved)
    summaries, pairs = summarize_rows(config, rows)
    metadata = {
        **metadata,
        "analysis": {
            "source_sha256": {
                name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in ("study_report.py", "study_analysis.py", "study_plots.py")
            },
            "requirements_lock_sha256": hashlib.sha256(
                (ROOT / "requirements.lock").read_bytes()
            ).hexdigest(),
            "dependencies": {
                name: version(name)
                for name in ("numpy", "matplotlib", "pydantic", "PyYAML", "pandas")
            },
        },
    }
    config.out.mkdir(parents=True, exist_ok=True)
    for name, data in (("solutions", solutions), ("design", design), ("metadata", metadata)):
        (config.out / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False) + "\n", "utf-8"
        )
    if "E6" in config.experiments:
        compatible = [
            {
                **solutions[d["job_id"]],
                "algoritmo": (
                    f"ga_{d['configuration']}"
                    if solutions[d["job_id"]]["algoritmo"] == "ga"
                    else solutions[d["job_id"]]["algoritmo"]
                ),
            }
            for d in design
            if d["experiment"] == "E6"
        ]
        (config.out / "e6_solutions.json").write_text(
            json.dumps(compatible, ensure_ascii=False) + "\n", "utf-8"
        )
    _csv(config.out / "metrics.csv", rows)
    _csv(config.out / "summary.csv", summaries)
    _csv(config.out / "paired.csv", pairs)
    convergence = [
        {**entry, "passo": step, "fitness": value}
        for entry in design
        for step, value in enumerate(solutions[entry["job_id"]]["historico_fitness"])
    ]
    (config.out / "convergence").mkdir(exist_ok=True)
    for exp in config.experiments:
        _csv(
            config.out / "convergence" / f"{exp}.csv.gz",
            [r for r in convergence if r["experiment"] == exp],
        )
    (config.out / "convergence.csv").unlink(missing_ok=True)
    lines = [
        "# E1–E6 — tabelas da rodada de 23/10",
        "",
        "Cinco seeds por configuração; dp amostral. Fitness comum usa os pesos oficiais.",
        "Em E5, fitness objetivo é específico de cada perfil e não deve ordenar os perfis.",
        "V/E/D compara fitness comum por seed. Tempo foi medido sob concorrência.",
        "",
    ]
    for exp, experiment in config.experiments.items():
        lines.extend([f"## {exp} — {experiment.title}", ""])
        for instance in dict.fromkeys(r["instance_nome"] for r in rows):
            lines.extend(
                [
                    f"### {instance}",
                    "",
                    "| Configuração | Fitness comum ± dp | Melhor comum | Fitness objetivo ± dp | "
                    "Custo operacional ± dp | Prioridade comum ± dp | Tempo s ± dp | "
                    "Violação % (hard) | V/E/D |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for s in summaries:
                if s["experiment"] != exp or s["instance_nome"] != instance:
                    continue
                cells = [
                    f"{s[m + '_media']:.2f} ± {s[m + '_dp']:.2f}"
                    for m in (
                        "fitness_comum",
                        "fitness",
                        "custo_operacional",
                        "prioridade_comum",
                        "tempo_exec_s",
                    )
                ]
                lines.append(
                    f"| {s['configuration']} | {cells[0]} | {s['fitness_comum_min']:.2f} | "
                    f"{cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} | "
                    f"{s['execucoes_com_violacao_pct']:.0f} "
                    f"({s['execucoes_com_violacao_hard_pct']:.0f}) | "
                    f"{s['vitoria']}/{s['empate']}/{s['derrota']} |"
                )
            lines.append("")
        lines.extend([f"![{exp}](../figuras/s3/{exp.lower()}.png)", ""])
    (config.out / "resumo.md").write_text("\n".join(lines), "utf-8")
    render_figures(config, solutions, design, summaries)
    files = [
        *config.out.glob("*.csv"),
        *config.out.glob("*.json"),
        *config.out.glob("convergence/*.csv.gz"),
        *config.out.glob("provenance/*"),
        *config.out.glob("evidencias/*"),
        config.out / "resumo.md",
        *config.figures.glob("*.png"),
        *config.figures.glob("*.pdf"),
    ]
    validation = {
        "unique_solutions_validated": len(solutions),
        "observations": len(rows),
        "compatibility_audit": {
            "unique_runs_with_duplicate_attributes": len(
                {r["job_id"] for r in rows if r["incompatibilidades_duplicadas"] > 0}
            ),
            "max_duplicate_attributes": max(r["incompatibilidades_duplicadas"] for r in rows),
            "note": "Base 86276b9 conta atributos; fitness_sem_duplicacao audita entregas únicas.",
        },
        "checks": [
            "entregas",
            "veículos",
            "km",
            "cargas",
            "custos",
            "horários",
            "violações P0/P1",
            "penalidades",
            "fitness",
            "curvas",
            "seeds",
        ],
        "sha256_artifacts": {
            str(p.relative_to(_artifact_root(config))): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
            if p.name != "validacao.json"
        },
    }
    (config.out / "validacao.json").write_text(json.dumps(validation, indent=2) + "\n", "utf-8")


def _artifact_root(config: StudyConfig) -> Path:
    """Ancestral comum para caminhos portáveis no manifesto de artefatos."""
    import os

    return Path(os.path.commonpath([config.out, config.figures]))
