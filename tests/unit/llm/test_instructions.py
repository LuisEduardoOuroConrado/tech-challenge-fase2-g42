import json
import logging
from pathlib import Path

import pytest

from medroute.constraints import cronograma_rota, duracao_rota
from medroute.data.distance import DistanceMatrix
from medroute.data.loader import load_fleet, load_instance
from medroute.domain.models import Solution
from medroute.llm import (
    MockClient,
    build_route_contexts,
    generate_instructions,
    load_prompt,
)
from medroute.llm.instructions import AVISO_NOVA_TENTATIVA, fallback_instructions, is_faithful
from medroute.llm.text import hora

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "solution_sp15.json"
SP15 = ROOT / "data" / "instances" / "sp_15.json"
FROTA = ROOT / "configs" / "frota.yaml"


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
        self.prompts = []

    def complete(self, system, user, *, prompt=None):
        self.calls.append((system, user))
        self.prompts.append(prompt)
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
    (_, primeira), (_, segunda) = client.calls
    assert segunda == f"{primeira}\n\n{AVISO_NOVA_TENTATIVA}"  # muda a chave do cache
    assert {p.nome for p in client.prompts} == {"instrucoes_motorista"}


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


def test_fidelidade_ignora_espacos_e_hifens_tipograficos(solution, inst):
    # Visto com o gpt-oss no Groq em 13/10: "Domicílio<U+202F>02" reprovava uma resposta correta.
    van = build_route_contexts(solution, inst)[2]
    resposta = (
        "1. IPq HC\u2011FMUSP\n2. Domicílio\u202f02\n3. Domicílio\u00a005\n"
        "4. Domicílio  08\n5. Domicílio 10"
    )
    assert is_faithful(resposta, van)


def test_instrucoes_saem_sem_espacos_tipograficos(solution, inst):
    solution = solution.model_copy(update={"routes": solution.routes[:1]})
    resposta = (
        "InCor, Instituto da Criança (ICr), Domicílio\u202f03, Domicílio\u202f06: 31,8\u202fkm"
    )
    client = ScriptedClient(resposta)

    texto = generate_instructions(solution, inst, client)["moto-01"]

    assert len(client.calls) == 1  # aceita de primeira, sem nova tentativa
    assert texto == resposta.replace("\u202f", " ")


def test_fallback_lista_alertas_e_retorno(solution, inst):
    ctx = build_route_contexts(solution, inst)[0]
    texto = fallback_instructions(ctx)

    assert texto.startswith("### Rota moto-01 (moto)")
    assert "**Atenção**" in texto
    assert "3. Domicílio 03" in texto
    assert texto.endswith(f"volte ao depósito {inst.depot.nome} ao final.")
    assert "chegada prevista" not in texto  # sem frota, sem horários


# --- horários de chegada (prompt v2) ------------------------------------------


@pytest.fixture
def fleet():
    return load_fleet(FROTA)


@pytest.mark.parametrize(
    ("minuto", "esperado"), [(420, "07:00"), (462.4, "07:42"), (479.6, "08:00"), (1440, "00:00")]
)
def test_hora_formata_minuto_do_dia(minuto, esperado):
    assert hora(minuto) == esperado


def test_com_frota_o_contexto_traz_o_cronograma_de_chegada(solution, inst, fleet):
    moto = build_route_contexts(solution, inst, fleet)[0]
    dm = DistanceMatrix(inst, fleet)
    veiculo = next(v for v in inst.fleet if v.id == "moto-01")
    args = (dm, veiculo, solution.routes[0].sequence, inst, fleet, fleet.saida_min)
    chegadas = cronograma_rota(*args)

    assert moto.saida_min == 420  # inicio_jornada 07:00
    assert [p.chegada_min for p in moto.paradas] == [chegadas[p.id] for p in moto.paradas]
    assert moto.duracao_min == duracao_rota(*args)

    dados = json.loads(moto.to_prompt_json())
    assert (dados["resumo"]["saida"], dados["resumo"]["retorno"]) == ("07:00", "09:19")
    assert [p["chegada"] for p in dados["paradas"]] == ["07:00", "07:12", "08:01", "08:47"]
    assert "prazo de 180 min após a saída (até 10:00)" in dados["alertas"][0]


def test_sem_frota_o_contexto_nao_tem_horarios(solution, inst):
    dados = json.loads(build_route_contexts(solution, inst)[0].to_prompt_json())
    assert "saida" not in dados["resumo"] and "retorno" not in dados["resumo"]
    assert all("chegada" not in p for p in dados["paradas"])


def test_fidelidade_com_horarios_exige_o_horario_depois_de_cada_nome(solution, inst, fleet):
    ctx = build_route_contexts(solution, inst, fleet)[0]
    certo = (
        "1. InCor — 07:00\n2. Instituto da Criança (ICr) — 07:12\n"
        "3. Domicílio 03 — 08:01\n4. Domicílio 06 — 08:47"
    )
    errado = certo.replace("08:01", "08:10")
    sem_horario = certo.replace(" — 08:47", "")
    antes_do_nome = certo.replace("4. Domicílio 06 — 08:47", "4. 08:47 Domicílio 06")

    assert is_faithful(certo, ctx)
    for resposta in (errado, sem_horario, antes_do_nome):
        assert not is_faithful(resposta, ctx)
        assert is_faithful(resposta, ctx, horarios=False)  # a ordem dos nomes está certa


def test_horario_errado_duas_vezes_usa_fallback_com_horarios(solution, inst, fleet):
    solution = solution.model_copy(update={"routes": solution.routes[:1]})
    so_nomes = "InCor, Instituto da Criança (ICr), Domicílio 03, Domicílio 06"
    client = ScriptedClient(so_nomes, so_nomes)

    texto = generate_instructions(solution, inst, client, fleet)["moto-01"]

    assert len(client.calls) == 2
    assert '"chegada":"07:12"' in client.calls[0][1]
    ctx = build_route_contexts(solution, inst, fleet)[0]
    assert texto == fallback_instructions(ctx)
    assert is_faithful(texto, ctx)
    assert "Saída de Farmácia Central HC-FMUSP às 07:00" in texto
    assert "2. Instituto da Criança (ICr) — chegada prevista às 07:12 — prioridade" in texto
    assert texto.endswith("ao final, com chegada prevista às 09:19.")
