from typer.testing import CliRunner

from medroute.app.cli import app

runner = CliRunner()


def test_demo_confirma_instalacao() -> None:
    result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0
    assert "medroute instalado e pronto para uso." in result.stdout
