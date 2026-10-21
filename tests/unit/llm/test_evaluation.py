import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from medroute.data.loader import load_instance
from medroute.domain.models import Solution
from medroute.llm import CachedClient, MockClient, OpenAICompatibleClient, build_route_contexts
from medroute.llm.evaluation import (
    Pergunta,
    RecordingClient,
    build_questions,
    evaluate_instructions,
    evaluate_qa,
    evaluate_report,
    extract_numbers,
    main,
    numbers_in_data,
    render_markdown,
    rescore,
    run_evaluation,
    score_qa,
    score_report,
    summarize,
    ungrounded_numbers,
)
from medroute.llm.qa import RECUSA, build_qa_context
from medroute.llm.reports import build_report_data, prompt_context

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "solution_sp15.json"
SP15 = ROOT / "data" / "instances" / "sp_15.json"

ANALISE = (
    "## Resumo executivo\nO plano custa R$ 584,24 por dia.\n\n"
    "## Eficiência e economia\nForam 122,6 km.\n\n"
    "## Recomendações\n- Manter.\n- Monitorar.\n- Revisar."
)


@pytest.fixture
def inst():
    return load_instance(SP15)


@pytest.fixture
def solution():
    return Solution.model_validate_json(FIXTURE.read_text("utf-8"))


class ScriptedClient:
    provider = "fake"
    model = "fake"

    def __init__(self, *respostas):
        self.respostas = list(respostas)

    def complete(self, system, user, *, prompt=None):
        return self.respostas.pop(0)


# --- números -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("R$ 1.586,65", [(1586.65, 2)]),
        ("31,8 km", [(31.8, 1)]),
        ("1.107,0 km", [(1107.0, 1)]),
        ("1.107 km", [(1107.0, 0)]),  # grupos de 3 dígitos: milhar
        ("31.8 km", [(31.8, 1)]),  # ponto decimal, por tolerância
        ("leva 126 min.", [(126.0, 0)]),
        ("53,0% e 297 min", [(53.0, 1), (297.0, 0)]),
    ],
)
def test_extrai_numeros_no_padrao_brasileiro(texto, esperado):
    assert [(v, c) for v, c, _ in extract_numbers(texto)] == esperado


def test_numeros_dos_dados_incluem_textos_e_ignoram_booleanos():
    dados = {"a": 1.5, "b": [2, {"c": "plano adotado R$ 1.093,50 menor (53,0%)"}], "d": True}
    assert sorted(numbers_in_data(dados)) == [1.5, 2.0, 53.0, 1093.5]


def test_numeros_com_fonte_aceitam_arredondamento_nomes_e_contagens():
    dados = {"custo": 970.55, "pct": 53.04, "km": 221.4}
    texto = "1. A moto-01 vai ao Domicílio 27: R$ 970,55, 53% menor, 221 km e 3 paradas.\n2. Fim."
    assert ungrounded_numbers(texto, dados, ["moto-01", "Domicílio 27"]) == []


def test_numeros_inventados_sao_apontados():
    dados = {"ocupacao": 96.8, "duracoes": [291, 181]}
    texto = "Manter a ocupação abaixo de 95 % e reduzir a rota em ~30 min (hoje 96,8%)."
    assert ungrounded_numbers(texto, dados) == ["95", "30"]


def test_diferenca_calculada_pelo_modelo_conta_como_sem_fonte():
    # 291 - 181 = 110 está certo, mas o prompt proíbe refazer contas.
    assert ungrounded_numbers("diferença de 110 min", {"d": [291, 181]}) == ["110"]


# --- gravação das chamadas ---------------------------------------------------


def test_gravacao_marca_respostas_do_cache(tmp_path):
    cached = CachedClient(ScriptedClient("primeira"), tmp_path)
    rec = RecordingClient(cached)

    rec.complete("s", "u")
    rec.complete("s", "u")

    assert [c.cache for c in rec.chamadas] == [False, True]
    assert rec.chamadas[0].segundos is not None
    assert rec.chamadas[1].segundos is None
    assert rec.chamadas[1].resposta == "primeira"


def test_gravacao_separa_espera_por_limite_do_tempo_do_modelo():
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    erro = openai.RateLimitError(
        "limite",
        response=httpx.Response(429, request=request, headers={"retry-after": "17"}),
        body=None,
    )
    respostas = [erro, SimpleNamespace(choices=[_choice("ok")])]

    def create(**_):
        item = respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client = OpenAICompatibleClient(
        provider="groq", api_key="k", model="m", sdk_client=sdk, sleep=lambda s: None
    )
    rec = RecordingClient(client)

    assert rec.complete("s", "u") == "ok"
    assert rec.chamadas[0].espera_limite_s == 17.0
    assert rec.chamadas[0].segundos < 17.0  # a espera não entra no tempo do modelo


def _choice(content):
    return SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")


# --- instruções --------------------------------------------------------------


def test_instrucoes_com_mock_passam_e_infieis_reprovam(solution, inst):
    resultados = evaluate_instructions(solution, inst, MockClient())
    assert [r.caso for r in resultados] == ["moto-01", "carro-01", "van-01"]
    assert all(r.aprovado for r in resultados)

    um = solution.model_copy(update={"routes": solution.routes[:1]})
    (ruim,) = evaluate_instructions(um, inst, ScriptedClient("só InCor", "também não"))
    assert not ruim.criterios["ordem_das_paradas"]
    assert ruim.tentativas == 2  # a avaliação olha a primeira resposta crua
    assert ruim.resposta == "só InCor"


def test_instrucoes_sem_alerta_de_critica_reprovam(solution, inst):
    um = solution.model_copy(update={"routes": solution.routes[:1]})
    ctx = build_route_contexts(um, inst)[0]
    texto = "\n".join(f"{p.ordem}. {p.nome}" for p in ctx.paradas)  # sem citar "crítica"

    (r,) = evaluate_instructions(um, inst, ScriptedClient(texto))

    assert r.criterios["ordem_das_paradas"]
    assert not r.criterios["alertas_citados"]
    assert not r.aprovado


# --- relatório ---------------------------------------------------------------


def test_relatorio_com_secoes_numeros_e_recomendacoes_passa(solution, inst):
    r = evaluate_report([solution], inst, "diario", ScriptedClient(ANALISE))

    assert r.aprovado
    assert r.criterios["recomendacoes_3_a_5"]
    assert not r.criterios["tamanho_200_a_350"]  # informativo: não reprova


def test_relatorio_pontua_secoes_recomendacoes_e_numeros(solution, inst):
    dados = prompt_context(build_report_data([solution], inst, "diario"))
    poucas = ANALISE.replace("- Monitorar.\n- Revisar.", "")
    inventado = ANALISE.replace("122,6 km", "999,9 km")
    sem_secao = ANALISE.replace("## Recomendações", "Recomendações")

    assert not score_report(poucas, dados, [])[0]["recomendacoes_3_a_5"]
    assert score_report(inventado, dados, [])[1] == ["999,9"]
    assert not score_report(sem_secao, dados, [])[0]["secoes"]


# --- Q&A -----------------------------------------------------------------------


def test_perguntas_vem_da_propria_solucao(solution, inst):
    perguntas = {p.caso: p for p in build_questions(solution, inst)}

    assert len(perguntas) == 10
    assert {p.tipo for p in perguntas.values()} == {"resposta", "indisponivel", "recusa"}
    localizar = perguntas["localizar_parada"]
    assert localizar.texto == "Qual veículo entrega no Domicílio 04 e em que posição da rota?"
    assert localizar.esperado == ["carro-01", 3.0]
    assert perguntas["custo_operacional"].esperado == [584.24]
    assert perguntas["buscar_por_id"].esperado == ["moto-01", "Domicílio 06", 3.3]


@pytest.mark.parametrize(
    ("tipo", "resposta", "ok"),
    [
        ("recusa", RECUSA, True),
        ("recusa", RECUSA.rstrip("."), True),
        ("recusa", f"{RECUSA} Mas posso dizer que...", False),
        ("indisponivel", "Essa informação não está disponível no plano.", True),
        ("indisponivel", "A hora de chegada não está informada no plano.", True),
        ("indisponivel", "Não há informação sobre combustível.", True),
        ("indisponivel", RECUSA, False),
        ("indisponivel", "Chega às 10h30.", False),
    ],
)
def test_comportamento_de_recusa_e_indisponivel(solution, inst, tipo, resposta, ok):
    contexto = build_qa_context(solution, inst)
    criterios, _ = score_qa(resposta, Pergunta("caso", "?", tipo), contexto, [])
    assert criterios["comportamento"] is ok


def test_resposta_precisa_ter_os_fatos_esperados(solution, inst):
    contexto = build_qa_context(solution, inst)
    pergunta = Pergunta("caso", "?", "resposta", ["carro-01", 3.0, 584.24])

    certa = "Está no carro-01, parada 3; o custo é R$ 584,24."
    errada = "Está no carro-01, parada 4; o custo é R$ 584,24."
    assert score_qa(certa, pergunta, contexto, ["carro-01"])[0]["comportamento"]
    assert not score_qa(errada, pergunta, contexto, ["carro-01"])[0]["comportamento"]


def test_qa_com_cliente_que_segue_o_prompt(solution, inst):
    perguntas = [
        Pergunta("custo", "Qual o custo operacional?", "resposta", [584.24]),
        Pergunta("tempo", "Vai chover?", "recusa"),
    ]
    client = ScriptedClient("O custo operacional é R$ 584,24.", RECUSA)

    resultados = evaluate_qa(solution, inst, client, perguntas)

    assert [r.aprovado for r in resultados] == [True, True]


# --- execução, reavaliação e resumo ------------------------------------------


def test_run_resume_e_renderiza_com_mock(solution, inst):
    resultados = run_evaluation({"mock": MockClient()}, [solution], inst)
    resumo = {r["tarefa"]: r for r in summarize(resultados)}

    assert [len([r for r in resultados if r.tarefa == t]) for t in resumo] == [3, 2, 10]
    assert resumo["instrucoes"]["aprovados_pct"] == 100.0
    md = render_markdown(summarize(resultados), resultados, ["- cabeçalho"])
    assert md.startswith("# Avaliação da LLM — rubrica automática\n\n- cabeçalho")
    assert "| mock/mock | 3 | 100,0% |" in md
    assert "## Casos reprovados" in md


def test_rescore_recalcula_criterios_e_mantem_respostas_e_tempos(solution, inst):
    resultados = run_evaluation({"mock": MockClient()}, [solution], inst)
    salvos = [asdict(r) for r in resultados]
    salvos[0]["segundos"] = 1.23
    salvos[0]["resposta"] = "resposta trocada, sem as paradas"

    novos = rescore(salvos, [solution], inst)

    assert novos[0].segundos == 1.23
    assert not novos[0].criterios["ordem_das_paradas"]
    assert [r.aprovado for r in novos[1:]] == [r.aprovado for r in resultados[1:]]


def test_main_grava_resultados_e_resumo(tmp_path, monkeypatch, solution):
    monkeypatch.chdir(tmp_path)  # isola de um .env local
    out = tmp_path / "aval"
    main(
        ["--solucoes", str(FIXTURE), "--inst", str(SP15), "--provedores", "mock", "--out", str(out)]
    )

    salvos = json.loads((out / "resultados.json").read_text("utf-8"))
    assert len(salvos) == 15
    resumo = (out / "resumo.md").read_text("utf-8")
    assert "- Prompts: instrucoes_motorista v1, relatorio v1, qa v1" in resumo

    main(
        ["--solucoes", str(FIXTURE), "--inst", str(SP15), "--out", str(out)]
        + ["--reavaliar", str(out / "resultados.json")]
    )
    assert json.loads((out / "resultados.json").read_text("utf-8")) == salvos
