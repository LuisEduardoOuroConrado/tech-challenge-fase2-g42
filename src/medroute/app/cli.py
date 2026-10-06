"""Interface de linha de comando do medroute."""

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
from medroute.ga import GAConfig, GeneticAlgorithm
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
    console.print(
        f"Fitness [bold]R$ {solution.fitness:.2f}[/bold] · custo operacional "
        f"R$ {solution.custo_operacional:.2f} · {solution.distancia_total_km:.1f} km · "
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
    out_dir: Annotated[Path, typer.Option(help="Pasta dos resultados.")] = RESULTS_DIR,
    mapa: Annotated[bool, typer.Option(help="Gera também o mapa HTML.")] = True,
    frota: FleetOption = FLEET_PATH,
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
        )
    except ValueError as error:
        console.print(f"[red]Configuração inválida:[/red] {error}")
        raise typer.Exit(1) from error

    with console.status("Otimizando..."):
        solution = GeneticAlgorithm(instance, dm, config).run(seed)
    _print_solution(solution)

    stem = f"{instance.nome}_ga_{'tsp' if veiculo else 'vrp'}_s{seed}"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(solution.model_dump_json(indent=2) + "\n", encoding="utf-8")
    console.print(f"Solução: {json_path}")
    if mapa:
        console.print(f"Mapa: {save_map(solution, instance, out_dir / f'{stem}.html')}")


@app.command(name="map")
def map_(
    solucao: Annotated[Path, typer.Argument(help="JSON da Solution.")],
    inst: Annotated[
        str | None,
        typer.Option("--inst", help="Instância; padrão: a indicada na solução."),
    ] = None,
    out: Annotated[
        Path | None, typer.Option(help="HTML de saída; padrão: ao lado do JSON.")
    ] = None,
    frota: FleetOption = FLEET_PATH,
) -> None:
    """Gera o mapa HTML de uma Solution salva."""
    try:
        solution = Solution.model_validate_json(solucao.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        console.print(f"[red]Solução inválida:[/red] {error}")
        raise typer.Exit(1) from error
    instance, _ = _load(inst or solution.instance_nome, frota)
    try:
        path = save_map(solution, instance, out or solucao.with_suffix(".html"))
    except ValueError as error:
        console.print(f"[red]Erro:[/red] {error}")
        raise typer.Exit(1) from error
    console.print(f"Mapa: {path}")
