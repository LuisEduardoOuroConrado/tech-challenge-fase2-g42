"""Interface de linha de comando do medroute."""

import typer
from rich.console import Console

app = typer.Typer(
    name="medroute",
    help="Otimização de rotas para distribuição hospitalar.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Disponibiliza os comandos da plataforma medroute."""


@app.command()
def demo() -> None:
    """Valida a instalação enquanto os módulos da demonstração são integrados."""
    console.print("[green]medroute instalado e pronto para uso.[/green]")
