import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from medroute.domain.models import Solution

ROOT = Path(__file__).resolve().parents[2]
APP = str(ROOT / "src" / "medroute" / "app" / "streamlit_app.py")


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Cópia mínima do repositório: o app usa os mesmos caminhos relativos da CLI."""
    shutil.copytree(ROOT / "configs", tmp_path / "configs")
    shutil.copytree(ROOT / "data" / "instances", tmp_path / "data" / "instances")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    return tmp_path


def _app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, at.exception
    return at


def _otimizar(at: AppTest, inst: str = "sp_15") -> AppTest:
    at.selectbox(key="inst").select(inst)
    at.selectbox(key="provedor").select("mock")
    at.slider(key="populacao").set_value(10)
    at.slider(key="geracoes").set_value(5)
    at.button(key="otimizar").click().run()
    assert not at.exception, at.exception
    return at


def test_app_abre_sem_solucao(workdir):
    at = _app()

    assert "Otimizar rotas" in at.info[0].value


def test_app_otimiza_e_mostra_metricas_rotas_e_mapa(workdir):
    at = _otimizar(_app())

    solution = at.session_state["solution"]
    assert solution.instance_nome == "sp_15"
    assert [m.label for m in at.metric] == [
        "Fitness",
        "Operacional",
        "Prioridade",
        "Distância",
        "Veículos",
    ]
    assert at.metric[0].value == f"R$ {solution.fitness:,.2f}"
    tabela = at.dataframe[0].value
    assert list(tabela["Veículo"]) == [route.vehicle_id for route in solution.routes]
    assert tabela["Entregas"].sum() == 15
    assert [t.label for t in at.tabs] == ["Mapa", "Rotas", "Instruções", "Relatório", "Perguntas"]


def test_app_gera_instrucoes_relatorio_e_resposta_com_mock(workdir):
    at = _otimizar(_app())
    solution = at.session_state["solution"]

    at.button(key="btn_instrucoes").click().run()
    assert sorted(at.session_state["instrucoes"]) == sorted(r.vehicle_id for r in solution.routes)

    at.radio(key="periodo").set_value("semanal").run()
    at.button(key="btn_relatorio").click().run()
    assert at.session_state["relatorio"].strip()

    at.text_input(key="pergunta").input("Qual rota custa mais caro?").run()
    at.button(key="btn_perguntar").click().run()
    assert at.session_state["resposta"].startswith("[mock]")
    assert "Qual rota custa mais caro?" in at.session_state["resposta"]
    assert not at.exception, at.exception


def test_app_carrega_solucao_salva(workdir):
    fixture = Solution.model_validate_json(
        (ROOT / "tests" / "fixtures" / "solution_sp15.json").read_text("utf-8")
    )
    resultados = workdir / "data" / "resultados"
    resultados.mkdir(parents=True)
    (resultados / "sp_15_fixture.json").write_text(fixture.model_dump_json(), encoding="utf-8")

    at = _app()
    at.selectbox(key="inst").select("sp_15").run()
    at.radio(key="origem").set_value("Usar solução salva").run()
    at.button(key="carregar").click().run()

    assert not at.exception, at.exception
    assert at.session_state["solution"] == fixture


def test_app_avisa_quando_nao_ha_solucao_salva(workdir):
    at = _app()
    at.radio(key="origem").set_value("Usar solução salva").run()

    assert any("medroute solve" in info.value for info in at.info)
