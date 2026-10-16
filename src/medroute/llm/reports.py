"""Relatório diário/semanal com recomendações (Spec 05, S2).

O Python calcula os indicadores, monta as tabelas e identifica os padrões; a LLM
escreve só o texto analítico (resumo, eficiência e recomendações).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from math import ceil
from typing import Any, Literal

from medroute.domain.models import Instance, Priority, Solution
from medroute.experiments.metrics import extract_metrics, improvement_pct

from .client import LLMClient
from .context import PRIORIDADE_ROTULO, build_route_contexts
from .prompts import load_prompt
from .text import clean_text, moeda, numero_br

logger = logging.getLogger(__name__)

Periodo = Literal["diario", "semanal"]

PROMPT = "relatorio"
TENTATIVAS = 2
PERIODOS = {"diario": "diário", "semanal": "semanal"}
SECOES = ("Resumo executivo", "Eficiência e economia", "Recomendações")
DIAS_UTEIS_SEMANA = 5

# Limites dos padrões que alimentam as recomendações.
OCUPACAO_BAIXA_PCT = 50
OCUPACAO_ALTA_PCT = 90
AUTONOMIA_ALTA_PCT = 80
DESBALANCEAMENTO = 1.5  # maior rota / menor rota, em duração

AVISO_NOVA_TENTATIVA = (
    "ATENÇÃO: a resposta anterior não trouxe as três seções pedidas. Responda com "
    'exatamente "## Resumo executivo", "## Eficiência e economia" e "## Recomendações", '
    "nesta ordem."
)


def generate_report(
    solutions: list[Solution],
    inst: Instance,
    periodo: Periodo,
    client: LLMClient,
) -> str:
    """Devolve o relatório em Markdown: tabelas calculadas em Python + análise da LLM.

    `solutions` são planos para a mesma instância (ex.: GA e baselines). O de menor
    fitness é o plano adotado; os demais entram como comparação.
    """
    dados = build_report_data(solutions, inst, periodo)
    prompt = load_prompt(PROMPT)
    system, user = prompt.render(
        periodo=dados["periodo"],
        orientacao=_orientacao(dados),
        contexto=json.dumps(prompt_context(dados), ensure_ascii=False, separators=(",", ":")),
    )

    origem = f"{client.provider}/{client.model} · prompt {prompt.nome} v{prompt.versao}"
    for tentativa in range(TENTATIVAS):
        mensagem = user if tentativa == 0 else f"{user}\n\n{AVISO_NOVA_TENTATIVA}"
        analise = clean_text(client.complete(system, mensagem, prompt=prompt)).strip()
        if has_sections(analise):
            break
    else:
        logger.warning(
            "relatório: resposta da LLM (%s/%s) sem as seções pedidas; usando o texto padrão",
            client.provider,
            client.model,
        )
        analise = fallback_analysis(dados)
        origem = "texto padrão, sem LLM"

    plano = dados["plano_adotado"]
    partes = [
        f"# Relatório {dados['periodo']} de entregas — {dados['instancia']['nome']}",
        f"_Plano adotado: {plano['algoritmo']} (seed {plano['seed']}) · Análise: {origem}_",
        render_tables(dados),
        analise,
    ]
    return "\n\n".join(partes) + "\n"


def has_sections(texto: str) -> bool:
    """True se as três seções aparecem como títulos Markdown, na ordem."""
    posicao = 0
    for secao in SECOES:
        match = re.compile(rf"^#{{2,3}}\s*{re.escape(secao)}\s*$", re.MULTILINE | re.IGNORECASE)
        encontrado = match.search(texto, posicao)
        if not encontrado:
            return False
        posicao = encontrado.end()
    return True


# --- dados (tudo calculado em Python) ----------------------------------------


def build_report_data(
    solutions: list[Solution], inst: Instance, periodo: Periodo
) -> dict[str, Any]:
    if periodo not in PERIODOS:
        raise ValueError(f"período inválido: {periodo!r} (use diario ou semanal)")
    if not solutions:
        raise ValueError("o relatório precisa de pelo menos uma solução")
    for solution in solutions:
        if solution.instance_nome != inst.nome:
            raise ValueError(
                f"a solução é da instância {solution.instance_nome!r}, não de {inst.nome!r}"
            )

    # Uma solução por algoritmo (a de menor fitness); a melhor de todas é o plano adotado.
    melhores: dict[str, Solution] = {}
    for solution in solutions:
        atual = melhores.get(solution.algoritmo)
        if atual is None or solution.fitness < atual.fitness:
            melhores[solution.algoritmo] = solution
    adotado, *outras = sorted(melhores.values(), key=lambda s: s.fitness)

    plano = _resumo(adotado, inst)
    rotas = _rotas(adotado, inst)
    alternativas = []
    for outra in outras:
        alternativa = _resumo(outra, inst)
        alternativa["economia_do_adotado"] = _economia(plano, alternativa)
        alternativas.append(alternativa)

    prioridades = Counter(d.prioridade for d in inst.deliveries)
    dados: dict[str, Any] = {
        "periodo": PERIODOS[periodo],
        "instancia": {
            "nome": inst.nome,
            "deposito": inst.depot.nome,
            "entregas": len(inst.deliveries),
            "entregas_por_prioridade": {
                PRIORIDADE_ROTULO[p]: prioridades[p] for p in Priority if prioridades[p]
            },
            "entregas_refrigeradas": sum(d.refrigerado for d in inst.deliveries),
            "frota_disponivel": _frota(inst),
        },
        "plano_adotado": plano,
        "rotas": rotas,
        "alternativas": alternativas,
        "padroes": _padroes(adotado, inst, plano, rotas, alternativas),
    }
    if periodo == "semanal":
        dados["projecao_semanal"] = _projecao(plano, alternativas)
    return dados


def _frota(inst: Instance) -> dict[str, dict[str, Any]]:
    """Por tipo de veículo: quantidade, capacidade e custos (do primeiro veículo do tipo)."""
    frota: dict[str, dict[str, Any]] = {}
    for v in inst.fleet:
        tipo = frota.setdefault(
            v.tipo.value,
            {
                "quantidade": 0,
                "capacidade_kg": v.capacidade_kg,
                "capacidade_l": v.capacidade_l,
                "custo_fixo_dia": v.custo_fixo,
                "custo_km": v.custo_km,
            },
        )
        tipo["quantidade"] += 1
    return frota


def _resumo(solution: Solution, inst: Instance) -> dict[str, Any]:
    m = extract_metrics(solution)
    penalidades = float(m["penalidade_total"])
    entregas = int(m["entregas_atendidas"])
    return {
        "algoritmo": solution.algoritmo,
        "seed": solution.seed,
        "custo_generalizado": round(solution.fitness, 2),
        "custo_operacional": round(solution.custo_operacional, 2),
        # Spec 03: fitness = operacional + prioridade + penalidades.
        "custo_prioridade": round(
            max(0.0, solution.fitness - solution.custo_operacional - penalidades), 2
        ),
        "penalidades": round(penalidades, 2),
        "distancia_km": round(solution.distancia_total_km, 1),
        "duracao_total_min": round(float(m["duracao_total_min"])),
        "duracao_maior_rota_min": round(float(m["duracao_max_min"])),
        "veiculos_utilizados": m["veiculos_utilizados"],
        "veiculos_disponiveis": len(inst.fleet),
        "entregas_atendidas": entregas,
        "custo_operacional_por_entrega": (
            round(solution.custo_operacional / entregas, 2) if entregas else 0.0
        ),
        "rotas_com_violacao": m["rotas_com_violacao"],
    }


def _rotas(solution: Solution, inst: Instance) -> list[dict[str, Any]]:
    veiculos = {v.id: v for v in inst.fleet}
    rotas = []
    for ctx in build_route_contexts(solution, inst):
        veiculo = veiculos[ctx.vehicle_id]
        rotas.append(
            {
                "veiculo": ctx.vehicle_id,
                "tipo": ctx.vehicle_tipo.value,
                "paradas": len(ctx.paradas),
                "distancia_km": round(ctx.distancia_km, 1),
                "duracao_min": round(ctx.duracao_min),
                "custo": round(ctx.custo, 2),
                "ocupacao_peso_pct": round(100 * ctx.carga_kg / veiculo.capacidade_kg, 1),
                "ocupacao_volume_pct": round(100 * ctx.carga_l / veiculo.capacidade_l, 1),
                "uso_autonomia_pct": round(100 * ctx.distancia_km / veiculo.autonomia_km, 1),
                "paradas_criticas": [
                    p.ordem for p in ctx.paradas if p.prioridade is Priority.CRITICA
                ],
                "violacoes": {k: round(v, 2) for k, v in ctx.violacoes.items()},
            }
        )
    return rotas


def _economia(plano: dict[str, Any], alternativa: dict[str, Any]) -> dict[str, Any]:
    """Quanto o plano adotado é melhor que a alternativa (positivo = adotado melhor)."""
    economia: dict[str, Any] = {}
    for chave, casas in (("custo_generalizado", 2), ("custo_operacional", 2), ("distancia_km", 1)):
        economia[chave] = round(alternativa[chave] - plano[chave], casas)
        pct = improvement_pct(plano[chave], alternativa[chave])
        economia[f"{chave}_pct"] = round(pct, 1) if pct is not None else None
    economia["duracao_maior_rota_min"] = (
        alternativa["duracao_maior_rota_min"] - plano["duracao_maior_rota_min"]
    )
    return economia


def _padroes(
    adotado: Solution,
    inst: Instance,
    plano: dict[str, Any],
    rotas: list[dict[str, Any]],
    alternativas: list[dict[str, Any]],
) -> list[str]:
    padroes = []

    usados = {r["veiculo"] for r in rotas}
    ociosos = [
        f"{v.id} (custo fixo de {moeda(v.custo_fixo)} por dia se acionado)"
        for v in inst.fleet
        if v.id not in usados
    ]
    if ociosos:
        padroes.append(f"Veículos disponíveis e não utilizados: {', '.join(ociosos)}.")

    for r in rotas:
        # A dimensão mais cheia (peso ou volume) é a que limita o veículo.
        ocupacao, dimensao = max(
            (r["ocupacao_peso_pct"], "peso"), (r["ocupacao_volume_pct"], "volume")
        )
        if ocupacao < OCUPACAO_BAIXA_PCT:
            padroes.append(
                f"{r['veiculo']} ({r['tipo']}) usa só {numero_br(ocupacao)}% da capacidade "
                f"de {dimensao}, a dimensão mais ocupada."
            )
        elif ocupacao >= OCUPACAO_ALTA_PCT:
            padroes.append(
                f"{r['veiculo']} ({r['tipo']}) está com {numero_br(ocupacao)}% da capacidade "
                f"de {dimensao}, perto do limite."
            )
        if r["uso_autonomia_pct"] >= AUTONOMIA_ALTA_PCT:
            padroes.append(
                f"{r['veiculo']} roda {numero_br(r['uso_autonomia_pct'])}% da autonomia."
            )
        tardias = [p for p in r["paradas_criticas"] if p > ceil(r["paradas"] / 2)]
        if tardias:
            posicoes = ", ".join(str(p) for p in tardias)
            padroes.append(
                f"{r['veiculo']}: entrega crítica na segunda metade da rota "
                f"(parada {posicoes} de {r['paradas']})."
            )

    if len(rotas) > 1:
        longa = max(rotas, key=lambda r: r["duracao_min"])
        curta = min(rotas, key=lambda r: r["duracao_min"])
        if curta["duracao_min"] > 0 and (
            longa["duracao_min"] >= DESBALANCEAMENTO * curta["duracao_min"]
        ):
            padroes.append(
                f"Rotas desbalanceadas: {longa['veiculo']} leva {longa['duracao_min']} min e "
                f"{curta['veiculo']} leva {curta['duracao_min']} min."
            )

    violacoes = {k: v for k, v in adotado.penalidades.items() if v > 0}
    if violacoes:
        itens = ", ".join(f"{k} ({moeda(v)})" for k, v in violacoes.items())
        padroes.append(f"O plano adotado tem penalidades por violação: {itens}.")
    else:
        padroes.append("O plano adotado não viola nenhuma restrição.")

    for alt in alternativas:
        e = alt["economia_do_adotado"]
        operacional = (
            f"{moeda(abs(e['custo_operacional']))} "
            f"{'menor' if e['custo_operacional'] >= 0 else 'maior'}"
        )
        padroes.append(
            f"Em relação a {alt['algoritmo']} ({alt['veiculos_utilizados']} veículo(s)), o plano "
            f"adotado ({plano['veiculos_utilizados']} veículo(s)) tem custo generalizado "
            f"{moeda(e['custo_generalizado'])} menor, custo operacional {operacional} e a maior "
            f"rota {e['duracao_maior_rota_min']} min mais curta."
        )
    return padroes


def _projecao(plano: dict[str, Any], alternativas: list[dict[str, Any]]) -> dict[str, Any]:
    projecao: dict[str, Any] = {
        "dias_uteis": DIAS_UTEIS_SEMANA,
        "premissa": "mesma demanda e mesmo plano em todos os dias úteis",
        "entregas": plano["entregas_atendidas"] * DIAS_UTEIS_SEMANA,
        "custo_operacional": round(plano["custo_operacional"] * DIAS_UTEIS_SEMANA, 2),
        "custo_generalizado": round(plano["custo_generalizado"] * DIAS_UTEIS_SEMANA, 2),
        "distancia_km": round(plano["distancia_km"] * DIAS_UTEIS_SEMANA, 1),
    }
    if alternativas:
        projecao["economia_custo_generalizado"] = {
            alt["algoritmo"]: round(
                alt["economia_do_adotado"]["custo_generalizado"] * DIAS_UTEIS_SEMANA, 2
            )
            for alt in alternativas
        }
    return projecao


# --- o que vai para a LLM ----------------------------------------------------


def prompt_context(dados: dict[str, Any]) -> dict[str, Any]:
    """Dados enviados à LLM: as diferenças numéricas com sinal viram frases prontas.

    Com `economia_do_adotado` em números (ex.: distância -52,3), o modelo trocava
    "maior" por "menor". As frases dizem a direção, então não há sinal a interpretar.
    """
    alternativas = []
    for alt in dados["alternativas"]:
        e = alt["economia_do_adotado"]
        alternativa = {k: v for k, v in alt.items() if k != "economia_do_adotado"}
        alternativa["plano_adotado_em_relacao_a_esta"] = {
            "custo_generalizado": _diferenca(
                e["custo_generalizado"], e["custo_generalizado_pct"], moeda
            ),
            "custo_operacional": _diferenca(
                e["custo_operacional"], e["custo_operacional_pct"], moeda
            ),
            "distancia": _diferenca(
                e["distancia_km"], e["distancia_km_pct"], lambda v: f"{numero_br(v)} km"
            ),
            "maior_rota": _diferenca(e["duracao_maior_rota_min"], None, lambda v: f"{v} min"),
        }
        alternativas.append(alternativa)
    return {**dados, "alternativas": alternativas}


def _diferenca(valor: float, pct: float | None, formatar) -> str:
    if valor == 0:
        return "igual"
    direcao = "menor" if valor > 0 else "maior"
    percentual = f" ({numero_br(abs(pct))}%)" if pct is not None else ""
    return f"plano adotado {formatar(abs(valor))} {direcao}{percentual}"


def _orientacao(dados: dict[str, Any]) -> str:
    entregas = dados["plano_adotado"]["entregas_atendidas"]
    projecao = dados.get("projecao_semanal")
    if not projecao:
        return f"Os dados descrevem um dia de operação ({entregas} entregas)."
    return (
        f"Os dados descrevem UM DIA típico de operação ({entregas} entregas por dia). "
        f"Os totais da semana ({projecao['entregas']} entregas em {projecao['dias_uteis']} "
        'dias úteis) estão em "projecao_semanal" e são estimativas.'
    )


# --- tabelas e texto padrão (sem LLM) ----------------------------------------


def _tabela(cabecalho: list[str], linhas: list[list[str]]) -> str:
    partes = ["| " + " | ".join(cabecalho) + " |", "|" + "---|" * len(cabecalho)]
    partes += ["| " + " | ".join(linha) + " |" for linha in linhas]
    return "\n".join(partes)


def render_tables(dados: dict[str, Any]) -> str:
    inst, plano = dados["instancia"], dados["plano_adotado"]
    prioridades = " · ".join(f"{p}: {n}" for p, n in inst["entregas_por_prioridade"].items())
    indicadores = [
        ["Entregas atendidas", f"{plano['entregas_atendidas']} de {inst['entregas']}"],
        ["Entregas por prioridade", prioridades],
        [
            "Veículos utilizados",
            f"{plano['veiculos_utilizados']} de {plano['veiculos_disponiveis']}",
        ],
        ["Distância total", f"{numero_br(plano['distancia_km'])} km"],
        ["Maior rota", f"{plano['duracao_maior_rota_min']} min"],
        ["Custo operacional", moeda(plano["custo_operacional"])],
        ["Custo por entrega", moeda(plano["custo_operacional_por_entrega"])],
        ["Custo de prioridade (espera)", moeda(plano["custo_prioridade"])],
        ["Penalidades", moeda(plano["penalidades"])],
        ["Custo generalizado", moeda(plano["custo_generalizado"])],
    ]
    secoes = ["## Indicadores", _tabela(["Indicador", "Valor"], indicadores)]

    rotas = [
        [
            f"{r['veiculo']} ({r['tipo']})",
            str(r["paradas"]),
            numero_br(r["distancia_km"]),
            str(r["duracao_min"]),
            f"{numero_br(r['ocupacao_peso_pct'])}%",
            f"{numero_br(r['ocupacao_volume_pct'])}%",
            moeda(r["custo"]),
        ]
        for r in dados["rotas"]
    ]
    cabecalho = ["Veículo", "Paradas", "km", "min", "Ocupação (peso)", "Ocupação (volume)", "Custo"]
    secoes += ["## Rotas do plano adotado", _tabela(cabecalho, rotas)]

    if dados["alternativas"]:
        linhas = [
            [
                f"**{p['algoritmo']}**" if p is plano else p["algoritmo"],
                str(p["veiculos_utilizados"]),
                numero_br(p["distancia_km"]),
                str(p["duracao_maior_rota_min"]),
                moeda(p["custo_operacional"]),
                moeda(p["custo_prioridade"]),
                moeda(p["penalidades"]),
                moeda(p["custo_generalizado"]),
            ]
            for p in [plano, *dados["alternativas"]]
        ]
        cabecalho = [
            "Algoritmo",
            "Veículos",
            "km",
            "Maior rota (min)",
            "Operacional",
            "Prioridade",
            "Penalidades",
            "Generalizado",
        ]
        secoes += ["## Comparação entre algoritmos", _tabela(cabecalho, linhas)]

    projecao = dados.get("projecao_semanal")
    if projecao:
        linhas = [
            ["Custo operacional", moeda(projecao["custo_operacional"])],
            ["Custo generalizado", moeda(projecao["custo_generalizado"])],
            ["Distância", f"{numero_br(projecao['distancia_km'])} km"],
        ]
        for algoritmo, valor in projecao.get("economia_custo_generalizado", {}).items():
            linhas.append([f"Economia de custo generalizado vs. {algoritmo}", moeda(valor)])
        secoes += [
            f"## Projeção semanal ({projecao['dias_uteis']} dias úteis)",
            f"_Estimativa: {projecao['premissa']}._",
            _tabela(["Indicador", "Valor"], linhas),
        ]
    return "\n\n".join(secoes)


def fallback_analysis(dados: dict[str, Any]) -> str:
    """Texto determinístico, sem LLM, usado quando a resposta não traz as seções."""
    inst, plano = dados["instancia"], dados["plano_adotado"]
    resumo = (
        f"O plano {plano['algoritmo']} atende {plano['entregas_atendidas']} de "
        f"{inst['entregas']} entregas com {plano['veiculos_utilizados']} de "
        f"{plano['veiculos_disponiveis']} veículos, em {numero_br(plano['distancia_km'])} km, "
        f"ao custo operacional de {moeda(plano['custo_operacional'])}."
    )
    if dados["alternativas"]:
        eficiencia = " ".join(
            f"Em relação a {alt['algoritmo']}, o custo generalizado é "
            f"{moeda(alt['economia_do_adotado']['custo_generalizado'])} menor."
            for alt in dados["alternativas"]
        )
    else:
        eficiencia = (
            f"O custo generalizado é de {moeda(plano['custo_generalizado'])}, dos quais "
            f"{moeda(plano['custo_prioridade'])} vêm do tempo de espera das entregas."
        )
    pontos = "\n".join(f"- Avaliar: {p}" for p in dados["padroes"])
    return "\n\n".join(
        [
            f"## {SECOES[0]}",
            resumo,
            f"## {SECOES[1]}",
            eficiencia,
            f"## {SECOES[2]}",
            "Pontos de atenção identificados automaticamente:",
            pontos,
        ]
    )
