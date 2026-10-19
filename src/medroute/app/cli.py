"""Interface de linha de comando do medroute."""

import json
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from medroute.data import (
    DataError,
    DistanceMatrix,
    generate_instance,
    load_fleet,
    load_instance,
    save_instance,
    validate_instance,
)
from medroute.data.cli import INSTANCIAS
from medroute.domain.models import Instance, Solution
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness
from medroute.viz import save_map

app = typer.Typer(
    name="medroute",
    help="Otimização de rotas para distribuição hospitalar.",
    no_args_is_help=True,
)
console = Console()

INSTANCES_DIR = Path("data/instances")
RESULTS_DIR = Path("data/resultados")
FLEET_PATH = Path("configs/frota.yaml")
FITNESS_PATH = Path("configs/fitness.yaml")
EXPERIMENT_PATH = Path("configs/experimentos/s2.yaml")

FleetOption = Annotated[Path, typer.Option("--frota", help="YAML da frota.")]


def _instance_path(inst: str) -> Path:
    """Aceita o nome da instância (`sp_15`) ou o caminho de um JSON."""
    path = Path(inst)
    return path if path.suffix == ".json" else INSTANCES_DIR / f"{inst}.json"


def _load(inst: str, frota: Path) -> tuple[Instance, DistanceMatrix]:
    try:
        fleet = load_fleet(frota)
        instance = load_instance(_instance_path(inst), fleet)
    except (DataError, FileNotFoundError) as error:
        console.print(f"[red]Erro ao carregar dados:[/red] {error}")
        raise typer.Exit(1) from error
    return instance, DistanceMatrix(instance, fleet)


def _print_solution(solution: Solution) -> None:
    table = Table(title=f"{solution.algoritmo} · {solution.instance_nome} · seed {solution.seed}")
    for column in ("Veículo", "Entregas", "km", "min", "Carga kg", "Custo R$", "Violações"):
        table.add_column(column, justify="left" if column == "Veículo" else "right")
    for route in solution.routes:
        violacoes = ", ".join(f"{k}={v:.2f}" for k, v in route.violacoes.items() if v) or "-"
        table.add_row(
            route.vehicle_id,
            str(len(route.sequence)),
            f"{route.distancia_km:.1f}",
            f"{route.duracao_min:.0f}",
            f"{route.carga_kg:.1f}",
            f"{route.custo:.2f}",
            violacoes,
        )
    console.print(table)
    penalidades = sum(solution.penalidades.values())
    prioridade = solution.fitness - solution.custo_operacional - penalidades
    console.print(
        f"Fitness [bold]R$ {solution.fitness:.2f}[/bold] = operacional "
        f"R$ {solution.custo_operacional:.2f} + prioridade R$ {prioridade:.2f} + penalidades "
        f"R$ {penalidades:.2f} · {solution.distancia_total_km:.1f} km · "
        f"{len(solution.historico_fitness)} gerações · {solution.tempo_exec_s:.2f} s"
    )


@app.callback()
def main() -> None:
    """Disponibiliza os comandos da plataforma medroute."""


@app.command()
def demo() -> None:
    """Valida a instalação enquanto os módulos da demonstração são integrados."""
    console.print("[green]medroute instalado e pronto para uso.[/green]")


@app.command()
def gen(
    out: Annotated[Path, typer.Option(help="Pasta de saída das instâncias.")] = INSTANCES_DIR,
    seed: Annotated[int, typer.Option(help="Seed do gerador.")] = 42,
    frota: FleetOption = FLEET_PATH,
) -> None:
    """Gera as instâncias padrão (sp_15, sp_40, sp_80) de forma reproduzível."""
    fleet = load_fleet(frota)
    out.mkdir(parents=True, exist_ok=True)
    for nome, (total, reais) in INSTANCIAS.items():
        instance = generate_instance(nome, total, reais, fleet, seed=seed)
        validate_instance(instance, fleet)
        path = out / f"{nome}.json"
        save_instance(instance, path)
        console.print(f"{nome}: {total} entregas ({reais} unidades reais) -> {path}")


@app.command()
def solve(
    inst: Annotated[str, typer.Option("--inst", help="Nome (sp_15) ou caminho do JSON.")],
    seed: Annotated[int, typer.Option(help="Seed do GA.")] = 42,
    veiculo: Annotated[
        str | None,
        typer.Option(help="Restringe a frota a um veículo (TSP), ex.: van-01."),
    ] = None,
    populacao: Annotated[int, typer.Option(help="Tamanho da população.")] = 100,
    geracoes: Annotated[int, typer.Option(help="Número máximo de gerações.")] = 300,
    crossover: Annotated[str, typer.Option(help="ox ou pmx.")] = "ox",
    mutacao: Annotated[str, typer.Option(help="swap, inversion ou two_opt.")] = "inversion",
    taxa_crossover: Annotated[float, typer.Option(help="Probabilidade de crossover.")] = 0.9,
    taxa_mutacao: Annotated[float, typer.Option(help="Probabilidade de mutação.")] = 0.2,
    elitismo: Annotated[int, typer.Option(help="Indivíduos preservados por geração.")] = 2,
    torneio: Annotated[int, typer.Option(help="Tamanho do torneio.")] = 3,
    paciencia: Annotated[int | None, typer.Option(help="Para após N gerações sem melhora.")] = None,
    semente_nn: Annotated[
        bool,
        typer.Option(
            help="Inclui a rota do vizinho mais próximo na população inicial (GA híbrido)."
        ),
    ] = True,
    busca_local: Annotated[
        float,
        typer.Option(help="Probabilidade de 2-opt dentro das rotas em cada filho (0 = GA puro)."),
    ] = 0.3,
    out_dir: Annotated[Path, typer.Option(help="Pasta dos resultados.")] = RESULTS_DIR,
    mapa: Annotated[bool, typer.Option(help="Gera também o mapa HTML.")] = True,
    frota: FleetOption = FLEET_PATH,
    pesos: Annotated[
        Path, typer.Option("--fitness", help="YAML com os pesos do fitness.")
    ] = FITNESS_PATH,
) -> None:
    """Otimiza as rotas com o GA e salva a Solution em JSON (e o mapa em HTML)."""
    instance, dm = _load(inst, frota)
    if veiculo is not None:
        selected = [vehicle for vehicle in instance.fleet if vehicle.id == veiculo]
        if not selected:
            ids = ", ".join(vehicle.id for vehicle in instance.fleet)
            console.print(f"[red]Veículo '{veiculo}' não está na frota:[/red] {ids}")
            raise typer.Exit(1)
        instance = instance.model_copy(update={"fleet": selected})

    try:
        config = GAConfig(
            population_size=populacao,
            generations=geracoes,
            crossover_rate=taxa_crossover,
            mutation_rate=taxa_mutacao,
            elitism=elitismo,
            tournament_size=torneio,
            crossover=crossover,
            mutation=mutacao,
            patience=paciencia,
            seed_nearest_neighbor=semente_nn,
            local_search_rate=busca_local,
        )
        fitness_cfg = load_fitness_config(pesos)
    except (ValueError, FileNotFoundError) as error:
        console.print(f"[red]Configuração inválida:[/red] {error}")
        raise typer.Exit(1) from error

    fitness_fn = make_fitness(instance, dm, load_fleet(frota), fitness_cfg)
    with console.status("Otimizando..."):
        solution = GeneticAlgorithm(instance, dm, config, fitness_fn).run(seed)
    _print_solution(solution)

    stem = f"{instance.nome}_ga_{'tsp' if veiculo else 'vrp'}_s{seed}"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(solution.model_dump_json(indent=2) + "\n", encoding="utf-8")
    console.print(f"Solução: {json_path}")
    if mapa:
        console.print(f"Mapa: {save_map(solution, instance, out_dir / f'{stem}.html')}")


def _load_solution(solucao: Path) -> Solution:
    try:
        return Solution.model_validate_json(solucao.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        console.print(f"[red]Solução inválida:[/red] {error}")
        raise typer.Exit(1) from error


SolutionArg = Annotated[Path, typer.Argument(help="JSON da Solution.")]
InstOption = Annotated[
    str | None,
    typer.Option("--inst", help="Instância; padrão: a indicada na solução."),
]
ProviderOption = Annotated[
    str | None,
    typer.Option(help="mock, groq ou openai; padrão: LLM_PROVIDER do .env."),
]


def _llm_client(provedor: str | None):
    """Cliente da LLM a partir do .env; `provedor` sobrescreve o LLM_PROVIDER."""
    from dotenv import load_dotenv

    from medroute.llm import client_from_env

    load_dotenv()
    env = dict(os.environ)
    if provedor is not None:
        env["LLM_PROVIDER"] = provedor
    return client_from_env(env)


def _load_solutions(paths: list[Path]) -> list[Solution]:
    """Lê Solutions de JSONs com uma Solution ou uma lista (o solutions.json do compare)."""
    solutions: list[Solution] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else [data]
            solutions += [Solution.model_validate(item) for item in items]
        except (OSError, ValueError) as error:
            console.print(f"[red]Solução inválida em {path}:[/red] {error}")
            raise typer.Exit(1) from error
    return solutions


@app.command(name="map")
def map_(
    solucao: SolutionArg,
    inst: InstOption = None,
    out: Annotated[
        Path | None, typer.Option(help="HTML de saída; padrão: ao lado do JSON.")
    ] = None,
    frota: FleetOption = FLEET_PATH,
) -> None:
    """Gera o mapa HTML de uma Solution salva."""
    solution = _load_solution(solucao)
    instance, _ = _load(inst or solution.instance_nome, frota)
    try:
        path = save_map(solution, instance, out or solucao.with_suffix(".html"))
    except ValueError as error:
        console.print(f"[red]Erro:[/red] {error}")
        raise typer.Exit(1) from error
    console.print(f"Mapa: {path}")


@app.command()
def instruct(
    solucao: SolutionArg,
    inst: InstOption = None,
    out: Annotated[
        Path | None,
        typer.Option(help="Markdown de saída; padrão: <solução>_instrucoes.md."),
    ] = None,
    provedor: ProviderOption = None,
    frota: FleetOption = FLEET_PATH,
) -> None:
    """Gera as instruções por motorista (LLM) de uma Solution salva."""
    from medroute.llm import LLMError, generate_instructions

    solution = _load_solution(solucao)
    instance, _ = _load(inst or solution.instance_nome, frota)

    try:
        client = _llm_client(provedor)
        with console.status(f"Gerando instruções ({client.provider})..."):
            instrucoes = generate_instructions(solution, instance, client)
    except LLMError as error:
        console.print(f"[red]Erro na LLM:[/red] {error}")
        raise typer.Exit(1) from error

    partes = [
        f"# Instruções de entrega — {solution.instance_nome}",
        f"_Solução: {solution.algoritmo} · seed {solution.seed} · LLM: "
        f"{client.provider}/{client.model}_",
    ]
    partes += [instrucoes[vid] for vid in instrucoes]
    texto = "\n\n".join(partes) + "\n"

    path = out or solucao.with_name(f"{solucao.stem}_instrucoes.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texto, encoding="utf-8")
    console.print(f"{len(instrucoes)} rota(s) com instruções -> {path}")


@app.command()
def compare(
    config: Annotated[
        Path, typer.Option("--config", help="YAML do experimento (configs/experimentos/).")
    ] = EXPERIMENT_PATH,
    seed: Annotated[
        list[int] | None,
        typer.Option("--seed", help="Sobrescreve as seeds do YAML; repita para várias."),
    ] = None,
    out: Annotated[
        Path | None, typer.Option(help="Pasta dos resultados; padrão: `out` do YAML.")
    ] = None,
) -> None:
    """Compara o GA com os baselines (NN, NN+2-opt, Savings, aleatório) via runner."""
    from medroute.experiments.runner import (
        ExperimentConfig,
        load_experiment_config,
        run_experiment,
        write_results,
    )

    try:
        cfg = load_experiment_config(config)
        updates = {}
        if out is not None:
            updates["out"] = out.resolve()
        if seed:
            updates["seeds"] = seed
        cfg = ExperimentConfig.model_validate({**cfg.model_dump(), **updates})
        with console.status("Rodando o experimento...") as status:
            result = run_experiment(cfg, progress=status.update)
        destination = write_results(result, cfg.out)
    except (OSError, ValueError) as error:
        console.print(f"[red]Experimento inválido:[/red] {error}")
        raise typer.Exit(1) from error

    table = Table(title=f"{cfg.name} · {len(cfg.seeds)} seed(s) · fitness em R$")
    for column in ("Instância", "Algoritmo"):
        table.add_column(column)
    for column in ("Média ± dp", "Melhor", "km", "Violação", "s"):
        table.add_column(column, justify="right")
    for row in result.summary:
        table.add_row(
            row["instance_nome"],
            row["algoritmo"],
            f"{row['fitness_media']:.2f} ± {row['fitness_dp']:.2f}",
            f"{row['fitness_min']:.2f}",
            f"{row['distancia_total_km_media']:.1f}",
            f"{row['percentual_execucoes_com_violacao']:.0f}%",
            f"{row['tempo_exec_s_media']:.1f}",
        )
    console.print(table)
    console.print(f"Resultados: {destination}")


@app.command()
def report(
    solucoes: Annotated[
        list[Path],
        typer.Argument(help="JSONs de Solution ou o solutions.json gerado pelo compare."),
    ],
    inst: Annotated[
        str | None,
        typer.Option("--inst", help="Instância; obrigatória se os JSONs tiverem mais de uma."),
    ] = None,
    periodo: Annotated[str, typer.Option(help="diario ou semanal.")] = "diario",
    out: Annotated[
        Path | None,
        typer.Option(help="Markdown de saída; padrão: <json>_relatorio_<periodo>.md."),
    ] = None,
    provedor: ProviderOption = None,
    frota: FleetOption = FLEET_PATH,
) -> None:
    """Gera o relatório diário ou semanal (LLM) comparando as Solutions de uma instância."""
    from medroute.llm import LLMError, generate_report

    if periodo not in ("diario", "semanal"):
        console.print(f"[red]Período inválido:[/red] {periodo} (use diario ou semanal)")
        raise typer.Exit(1)
    solutions = _load_solutions(solucoes)
    nomes = sorted({solution.instance_nome for solution in solutions})
    if inst is None and len(nomes) > 1:
        console.print(f"[red]Mais de uma instância nos JSONs; use --inst:[/red] {', '.join(nomes)}")
        raise typer.Exit(1)
    instance, _ = _load(inst or nomes[0], frota)
    solutions = [solution for solution in solutions if solution.instance_nome == instance.nome]
    if not solutions:
        console.print(f"[red]Nenhuma solução da instância {instance.nome}.[/red]")
        raise typer.Exit(1)

    try:
        client = _llm_client(provedor)
        with console.status(f"Gerando relatório ({client.provider})..."):
            texto = generate_report(solutions, instance, periodo, client)
    except LLMError as error:
        console.print(f"[red]Erro na LLM:[/red] {error}")
        raise typer.Exit(1) from error

    sufixo = f"_{instance.nome}" if len(nomes) > 1 else ""
    path = out or solucoes[0].with_name(f"{solucoes[0].stem}{sufixo}_relatorio_{periodo}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texto, encoding="utf-8")
    console.print(f"Relatório {periodo} ({len(solutions)} soluções) -> {path}")
