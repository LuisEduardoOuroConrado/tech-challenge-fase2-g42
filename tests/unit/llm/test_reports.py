import json
import logging
from pathlib import Path

import pytest

from medroute.data.loader import load_instance
from medroute.domain.models import Solution
from medroute.llm import MockClient, generate_report, load_prompt
from medroute.llm.reports import (
    AVISO_NOVA_TENTATIVA,
    build_report_data,
    fallback_analysis,
    has_sections,
    prompt_context,
    render_tables,
)
from medroute.llm.text import clean_text, moeda, numero_br

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "solution_sp15.json"
SP15 = ROOT / "data" / "instances" / "sp_15.json"

ANALISE = (
    "## Resumo executivo\nTudo certo.\n\n"
    "## Eficiência e economia\nEconomia boa.\n\n"
    "## Recomendações\n- Manter o plano."
)


@pytest.fixture
def inst():
    return load_instance(SP15)


@pytest.fixture
def ga():
    """Fixture da S0: 3 rotas, fitness 731,84, operacional 584,24, 122,6 km."""
    return Solution.model_validate_json(FIXTURE.read_text("utf-8"))


@pytest.fixture
def savings(ga):
    """Alternativa pior no custo, porém mais curta: uma van com todas as entregas."""
    van = ga.routes[2].model_copy(
        update={
            "sequence": [d for r in ga.routes for d in r.sequence],
            "distancia_km": 100.0,
            "duracao_min": 400.0,
            "custo": 650.0,
        }
    )
    return ga.model_copy(
        update={
            "algoritmo": "savings",
            "routes": [van],
            "fitness": 1500.0,
            "custo_operacional": 650.0,
            "distancia_total_km": 100.0,
        }
    )


class ScriptedClient:
    provider = "fake"
    model = "fake"

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.calls = []

    def complete(self, system, user, *, prompt=None):
        self.calls.append((system, user))
        return self.respostas.pop(0)


def sent_json(user: str) -> dict:
    return json.loads(user.split("Dados:\n", 1)[1].split("\n\nATENÇÃO")[0])


# --- critério 11 -------------------------------------------------------------


def test_duas_solucoes_com_mock_prompt_traz_metricas_e_texto_tem_recomendacoes(ga, savings, inst):
    client = MockClient()
    relatorio = generate_report([ga, savings], inst, "diario", client)

    assert len(client.calls) == 1
    dados = sent_json(client.calls[0][1])
    planos = {p["algoritmo"]: p for p in [dados["plano_adotado"], *dados["alternativas"]]}
    assert set(planos) == {"fixture_manual", "savings"}
    for plano in planos.values():
        assert {"custo_operacional", "distancia_km", "veiculos_utilizados"} <= set(plano)
        assert {"penalidades", "rotas_com_violacao"} <= set(plano)
    assert planos["fixture_manual"]["custo_operacional"] == 584.24
    assert planos["savings"]["veiculos_utilizados"] == 1

    assert relatorio.startswith("# Relatório diário de entregas — sp_15")
    assert "\n## Recomendações" in relatorio


# --- dados -------------------------------------------------------------------


def test_plano_adotado_e_o_de_menor_fitness_em_qualquer_ordem(ga, savings, inst):
    for solutions in ([ga, savings], [savings, ga]):
        dados = build_report_data(solutions, inst, "diario")
        assert dados["plano_adotado"]["algoritmo"] == "fixture_manual"
        assert [a["algoritmo"] for a in dados["alternativas"]] == ["savings"]


def test_varias_execucoes_do_mesmo_algoritmo_contam_uma_vez(ga, savings, inst):
    pior = ga.model_copy(update={"fitness": 900.0, "seed": 99})
    dados = build_report_data([pior, ga, savings], inst, "diario")

    assert dados["plano_adotado"]["seed"] == 17
    assert len(dados["alternativas"]) == 1


def test_resumo_decompoe_o_custo_generalizado(ga, inst):
    plano = build_report_data([ga], inst, "diario")["plano_adotado"]

    assert plano["custo_generalizado"] == 731.84
    assert plano["custo_operacional"] == 584.24
    assert plano["custo_prioridade"] == pytest.approx(731.84 - 584.24)  # Spec 03
    assert plano["penalidades"] == 0
    assert (plano["veiculos_utilizados"], plano["veiculos_disponiveis"]) == (3, 5)
    assert plano["entregas_atendidas"] == 15
    assert plano["custo_operacional_por_entrega"] == round(584.24 / 15, 2)


def test_instancia_resume_prioridades_e_frota(ga, inst):
    instancia = build_report_data([ga], inst, "diario")["instancia"]

    assert instancia["entregas_por_prioridade"] == {"crítica": 2, "alta": 4, "normal": 9}
    assert instancia["frota_disponivel"]["moto"]["quantidade"] == 2
    assert instancia["frota_disponivel"]["van"]["custo_fixo_dia"] == inst.fleet[-1].custo_fixo


def test_rotas_trazem_ocupacao_e_paradas_criticas(ga, inst):
    moto = build_report_data([ga], inst, "diario")["rotas"][0]
    veiculo = inst.fleet[0]

    assert moto["veiculo"] == "moto-01"
    assert moto["ocupacao_peso_pct"] == round(100 * 12.4 / veiculo.capacidade_kg, 1)
    assert moto["ocupacao_volume_pct"] == round(100 * 28.0 / veiculo.capacidade_l, 1)
    assert moto["paradas_criticas"] == [3, 4]


def test_padroes_apontam_ociosos_criticas_tardias_e_comparacao(ga, savings, inst):
    padroes = " ".join(build_report_data([ga, savings], inst, "diario")["padroes"])

    assert "não utilizados: moto-02 (custo fixo de R$" in padroes
    assert "carro-02" in padroes
    assert "moto-01: entrega crítica na segunda metade da rota (parada 3, 4 de 4)" in padroes
    assert "não viola nenhuma restrição" in padroes
    assert "Em relação a savings (1 veículo(s))" in padroes
    assert f"custo generalizado {moeda(1500 - 731.84)} menor" in padroes


def test_padroes_apontam_violacoes(ga, inst):
    violado = ga.model_copy(update={"penalidades": {"capacidade": 1200.0, "autonomia": 0.0}})
    padroes = build_report_data([violado], inst, "diario")["padroes"]

    assert "O plano adotado tem penalidades por violação: capacidade (R$ 1.200,00)." in padroes


@pytest.mark.parametrize(
    ("solutions", "periodo", "erro"),
    [
        ("vazia", "diario", "pelo menos uma"),
        ("outra", "diario", "sp_40"),
        ("ok", "mensal", "período inválido"),
    ],
)
def test_entradas_invalidas(ga, inst, solutions, periodo, erro):
    casos = {
        "vazia": [],
        "outra": [ga.model_copy(update={"instance_nome": "sp_40"})],
        "ok": [ga],
    }
    with pytest.raises(ValueError, match=erro):
        build_report_data(casos[solutions], inst, periodo)


# --- o que vai para a LLM ----------------------------------------------------


def test_contexto_do_prompt_troca_sinais_por_frases(ga, savings, inst):
    contexto = prompt_context(build_report_data([ga, savings], inst, "diario"))
    (alternativa,) = contexto["alternativas"]
    frases = alternativa["plano_adotado_em_relacao_a_esta"]

    assert "economia_do_adotado" not in alternativa
    assert frases["custo_generalizado"] == "plano adotado R$ 768,16 menor (51,2%)"
    assert frases["custo_operacional"] == "plano adotado R$ 65,76 menor (10,1%)"
    assert frases["distancia"] == "plano adotado 22,6 km maior (22,6%)"  # adotado roda mais
    assert frases["maior_rota"] == "plano adotado 267 min menor"


def test_diario_nao_tem_projecao_e_semanal_multiplica_por_cinco(ga, savings, inst):
    assert "projecao_semanal" not in build_report_data([ga, savings], inst, "diario")

    projecao = build_report_data([ga, savings], inst, "semanal")["projecao_semanal"]
    assert projecao["dias_uteis"] == 5
    assert projecao["entregas"] == 75
    assert projecao["custo_operacional"] == round(584.24 * 5, 2)
    assert projecao["distancia_km"] == round(122.6 * 5, 1)
    assert projecao["economia_custo_generalizado"] == {"savings": round((1500 - 731.84) * 5, 2)}


def test_prompt_semanal_separa_dia_e_semana(ga, inst):
    client = MockClient()
    relatorio = generate_report([ga], inst, "semanal", client)
    _, user = client.calls[0]

    assert "relatório semanal" in user
    assert "UM DIA típico de operação (15 entregas por dia)" in user
    assert "75 entregas em 5 dias úteis" in user
    assert relatorio.startswith("# Relatório semanal de entregas — sp_15")
    assert "## Projeção semanal (5 dias úteis)" in relatorio
    assert "_Estimativa: mesma demanda e mesmo plano em todos os dias úteis._" in relatorio


def test_prompt_do_relatorio_mantem_cifrao_e_exige_variaveis():
    prompt = load_prompt("relatorio")
    system, user = prompt.render(periodo="diário", orientacao="um dia", contexto="{}")

    assert "R$ 1.586,65" in system  # "$" que não é variável fica como está
    assert "$" not in user
    with pytest.raises(ValueError, match="contexto"):
        prompt.render(periodo="diário", orientacao="um dia")


# --- tabelas -----------------------------------------------------------------


def test_tabelas_usam_os_numeros_calculados(ga, savings, inst):
    tabelas = render_tables(build_report_data([ga, savings], inst, "diario"))

    assert "| Entregas atendidas | 15 de 15 |" in tabelas
    assert "| Veículos utilizados | 3 de 5 |" in tabelas
    assert "| Custo operacional | R$ 584,24 |" in tabelas
    assert "| Custo generalizado | R$ 731,84 |" in tabelas
    assert "| moto-01 (moto) | 4 | 31,8 | 74 |" in tabelas
    assert "## Comparação entre algoritmos" in tabelas
    assert "| **fixture_manual** | 3 | 122,6 |" in tabelas
    assert "| savings | 1 | 100,0 | 400 | R$ 650,00 |" in tabelas


def test_sem_alternativas_nao_ha_tabela_de_comparacao(ga, inst):
    tabelas = render_tables(build_report_data([ga], inst, "diario"))
    assert "Comparação entre algoritmos" not in tabelas


# --- análise da LLM, nova tentativa e fallback -------------------------------


def test_relatorio_junta_cabecalho_tabelas_e_analise_limpa(ga, inst):
    nbsp = chr(0x202F)
    client = ScriptedClient(ANALISE.replace("Economia boa", f"Economia de 51{nbsp}%"))

    relatorio = generate_report([ga], inst, "diario", client)

    assert len(client.calls) == 1
    versao = load_prompt("relatorio").versao
    assert f"· Análise: fake/fake · prompt relatorio v{versao}_" in relatorio
    assert relatorio.index("## Indicadores") < relatorio.index("## Resumo executivo")
    assert "Economia de 51 %" in relatorio
    assert nbsp not in relatorio
    assert relatorio.endswith("- Manter o plano.\n")


def test_resposta_sem_secoes_tenta_de_novo_com_aviso(ga, inst):
    client = ScriptedClient("Um texto corrido, sem títulos.", ANALISE)

    relatorio = generate_report([ga], inst, "diario", client)

    (_, primeira), (_, segunda) = client.calls
    assert segunda == f"{primeira}\n\n{AVISO_NOVA_TENTATIVA}"
    assert "Tudo certo." in relatorio


def test_resposta_sem_secoes_duas_vezes_usa_fallback(ga, savings, inst, caplog):
    client = ScriptedClient("sem títulos", "## Resumo executivo\nsó uma seção")

    with caplog.at_level(logging.WARNING):
        relatorio = generate_report([ga, savings], inst, "diario", client)

    dados = build_report_data([ga, savings], inst, "diario")
    assert fallback_analysis(dados) in relatorio
    assert has_sections(fallback_analysis(dados))
    assert "· Análise: texto padrão, sem LLM_" in relatorio
    assert "relatório" in caplog.text


def test_fallback_sem_alternativas_explica_o_custo(ga, inst):
    texto = fallback_analysis(build_report_data([ga], inst, "diario"))

    assert "O plano fixture_manual atende 15 de 15 entregas com 3 de 5 veículos" in texto
    assert "R$ 147,60 vêm do tempo de espera" in texto
    assert "- Avaliar: " in texto


def test_secoes_precisam_ser_titulos_e_estar_em_ordem():
    assert has_sections(ANALISE)
    assert has_sections(ANALISE.replace("## ", "### ").upper())
    assert not has_sections(ANALISE.replace("## Recomendações", "Recomendações"))
    fora_de_ordem = "## Recomendações\nx\n## Resumo executivo\nx\n## Eficiência e economia\nx"
    assert not has_sections(fora_de_ordem)
    assert not has_sections('Escreva "## Resumo executivo", "## Eficiência e economia"...')


# --- utilitários de texto ----------------------------------------------------


def test_numeros_no_padrao_brasileiro():
    assert numero_br(31.84) == "31,8"
    assert numero_br(1120.5) == "1.120,5"
    assert numero_br(1234567.891, 2) == "1.234.567,89"
    assert moeda(1586.65) == "R$ 1.586,65"
    assert moeda(0) == "R$ 0,00"


def test_clean_text_troca_espacos_e_hifens_tipograficos():
    sujo = "".join(["a", chr(0x00A0), "b", chr(0x2007), "c", chr(0x202F), "d", chr(0x2011), "e"])
    assert clean_text(sujo) == "a b c d-e"
    assert clean_text("travessão — fica") == "travessão — fica"
