import json
import logging
from pathlib import Path

import pytest

from medroute.data.loader import load_instance
from medroute.domain.models import Solution
from medroute.llm import (
    MockClient,
    build_route_contexts,
    generate_instructions,
    load_prompt,
)
from medroute.llm.instructions import fallback_instructions, is_faithful

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "solution_sp15.json"
SP15 = ROOT / "data" / "instances" / "sp_15.json"


@pytest.fixture
def inst():
    return load_instance(SP15)


@pytest.fixture
def solution():
    return Solution.model_validate_json(FIXTURE.read_text("utf-8"))


def with_route(solution, index, **changes):
    routes = list(solution.routes)
    routes[index] = routes[index].model_copy(update=changes)
    return solution.model_copy(update={"routes": routes})


class ScriptedClient:
    """Cliente falso que devolve as respostas na ordem dada."""

    provider = "fake"
    model = "fake"

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.respostas.pop(0)


# --- contexto ----------------------------------------------------------------


def test_contexto_da_fixture_segue_a_ordem_e_usa_dados_da_instancia(solution, inst):
    contexts = build_route_contexts(solution, inst)

    assert [c.vehicle_id for c in contexts] == ["moto-01", "carro-01", "van-01"]
    assert sum(len(c.paradas) for c in contexts) == 15
    moto = contexts[0]
    assert [p.id for p in moto.paradas] == solution.routes[0].sequence
    assert [p.ordem for p in moto.paradas] == [1, 2, 3, 4]
    assert moto.paradas[0].nome == "InCor"
    assert moto.paradas[2].prioridade == "critica"
    assert moto.deposito == inst.depot.nome
    assert moto.violacoes == {}


def test_entrega_inexistente_gera_erro_com_o_id(solution, inst):
    solution = with_route(solution, 0, sequence=["entrega-01", "entrega-99"])
    with pytest.raises(ValueError, match="entrega-99"):
        build_route_contexts(solution, inst)


def test_veiculo_inexistente_gera_erro(solution, inst):
    with pytest.raises(ValueError, match="caminhao-01"):
        build_route_contexts(with_route(solution, 0, vehicle_id="caminhao-01"), inst)


def test_instancia_diferente_gera_erro(solution, inst):
    with pytest.raises(ValueError, match="sp_40"):
        build_route_contexts(solution.model_copy(update={"instance_nome": "sp_40"}), inst)


def test_rota_vazia_e_ignorada(solution, inst):
    contexts = build_route_contexts(with_route(solution, 0, sequence=[]), inst)
    assert [c.vehicle_id for c in contexts] == ["carro-01", "van-01"]


def test_apenas_violacoes_positivas_entram_no_contexto(solution, inst):
    violacoes = {"capacidade": 0.0, "autonomia": 12.5}
    contexts = build_route_contexts(with_route(solution, 0, violacoes=violacoes), inst)
    assert contexts[0].violacoes == {"autonomia": 12.5}
    assert "Violação de autonomia: 12,5 acima do limite" in contexts[0].alertas()


def test_json_do_prompt_e_compacto_e_arredondado(solution, inst):
    moto = build_route_contexts(solution, inst)[0]
    dados = json.loads(moto.to_prompt_json())

    assert dados["veiculo"] == {"id": "moto-01", "tipo": "moto"}
    assert dados["resumo"]["paradas"] == 4
    assert [p["nome"] for p in dados["paradas"]] == [p.nome for p in moto.paradas]
    assert "deadline_min" not in dados["paradas"][0]  # None é omitido
    assert dados["paradas"][2]["deadline_min"] == 180
    assert dados["paradas"][2]["prioridade"] == "crítica"
    assert '": ' not in moto.to_prompt_json()  # sem espaços após ':'
    assert "Instituto da Criança" in moto.to_prompt_json()  # acentos sem \u escapes


# --- prompt ------------------------------------------------------------------


def test_prompt_de_instrucoes_tem_versao_e_secoes():
    prompt = load_prompt("instrucoes_motorista")
    assert prompt.versao >= 1
    assert "português do Brasil" in prompt.system
    assert "$contexto" in prompt.user


def test_render_substitui_variavel_sem_quebrar_chaves_do_json():
    system, user = load_prompt("instrucoes_motorista").render(contexto='{"a":{"b":1}}')
    assert '{"a":{"b":1}}' in user
    assert "$contexto" not in user


def test_render_sem_variavel_gera_erro():
    with pytest.raises(ValueError, match="contexto"):
        load_prompt("instrucoes_motorista").render()


@pytest.mark.parametrize(
    "conteudo",
    [
        "## system\noi\n## user\noi\n",  # sem cabeçalho
        "---\nversao: 0\n---\n## system\noi\n## user\noi\n",
        "---\nversao: 1\n---\n## system\noi\n",  # sem user
    ],
)
def test_prompt_mal_formatado_gera_erro(tmp_path, conteudo):
    (tmp_path / "ruim.md").write_text(conteudo, encoding="utf-8")
    with pytest.raises(ValueError):
        load_prompt("ruim", pasta=tmp_path)


# --- instruções --------------------------------------------------------------


def test_uma_chamada_por_rota_com_mock(solution, inst):
    client = MockClient()
    instrucoes = generate_instructions(solution, inst, client)

    assert list(instrucoes) == ["moto-01", "carro-01", "van-01"]
    assert len(client.calls) == 3
    assert all(texto.startswith("[mock]") for texto in instrucoes.values())


def test_prompt_enviado_contem_as_paradas_na_ordem_da_rota(solution, inst):
    client = MockClient()
    generate_instructions(solution, inst, client)

    nomes = {d.id: d.nome for d in inst.deliveries}
    for route, (_, user) in zip(solution.routes, client.calls, strict=True):
        posicoes = [user.index(f'"nome":"{nomes[i]}"') for i in route.sequence]
        assert posicoes == sorted(posicoes), route.vehicle_id


def test_prompt_marca_entregas_criticas_e_refrigeradas(solution, inst):
    client = MockClient()
    generate_instructions(solution, inst, client)
    _, user_moto = client.calls[0]
    _, user_carro = client.calls[1]

    assert "entrega CRÍTICA, prazo de 180 min" in user_moto
    assert "carga REFRIGERADA" in user_carro  # entrega-02 (ICESP)


def test_resposta_infiel_tenta_de_novo_e_usa_a_segunda(solution, inst):
    solution = solution.model_copy(update={"routes": solution.routes[:1]})
    boa = "InCor, Instituto da Criança (ICr), Domicílio 03, Domicílio 06"
    client = ScriptedClient("só InCor", boa)

    assert generate_instructions(solution, inst, client) == {"moto-01": boa}
    assert len(client.calls) == 2


def test_resposta_infiel_duas_vezes_usa_fallback(solution, inst, caplog):
    solution = solution.model_copy(update={"routes": solution.routes[:1]})
    client = ScriptedClient("só InCor", "também só InCor")

    with caplog.at_level(logging.WARNING):
        texto = generate_instructions(solution, inst, client)["moto-01"]

    ctx = build_route_contexts(solution, inst)[0]
    assert texto == fallback_instructions(ctx)
    assert is_faithful(texto, ctx)
    assert "moto-01" in caplog.text


def test_fidelidade_exige_a_ordem(solution, inst):
    ctx = build_route_contexts(solution, inst)[0]
    em_ordem = "InCor -> Instituto da Criança (ICr) -> Domicílio 03 -> Domicílio 06"
    fora_de_ordem = "Instituto da Criança (ICr) -> InCor -> Domicílio 03 -> Domicílio 06"

    assert is_faithful(em_ordem, ctx)
    assert is_faithful(em_ordem.upper(), ctx)
    assert not is_faithful(fora_de_ordem, ctx)


def test_fallback_lista_alertas_e_retorno(solution, inst):
    ctx = build_route_contexts(solution, inst)[0]
    texto = fallback_instructions(ctx)

    assert texto.startswith("### Rota moto-01 (moto)")
    assert "**Atenção**" in texto
    assert "3. Domicílio 03" in texto
    assert texto.endswith(f"volte ao depósito {inst.depot.nome} ao final.")
