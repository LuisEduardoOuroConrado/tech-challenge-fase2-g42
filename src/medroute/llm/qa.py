"""Perguntas em linguagem natural sobre o plano de rotas (Spec 05, S3).

Context stuffing: o Python monta o contexto completo da solução (resumo, rotas com
as paradas em ordem e observações) e a LLM responde só a partir dele.
"""

from __future__ import annotations

import json
import re
from typing import Any

from medroute.domain.models import Instance, Solution

from .client import LLMClient
from .context import PRIORIDADE_ROTULO, build_route_contexts
from .prompts import load_prompt
from .reports import build_report_data
from .text import clean_text

PROMPT = "qa"
MAX_PERGUNTA = 500  # caracteres
RECUSA = "Só posso responder perguntas sobre as rotas e entregas deste plano."

_TAG_PERGUNTA = re.compile(r"</?\s*pergunta\s*>", re.IGNORECASE)


def answer(question: str, solution: Solution, inst: Instance, client: LLMClient) -> str:
    """Responde à pergunta em Markdown curto, usando só os dados da solução."""
    pergunta = normalize_question(question)
    contexto = json.dumps(
        build_qa_context(solution, inst), ensure_ascii=False, separators=(",", ":")
    )
    prompt = load_prompt(PROMPT)
    system, user = prompt.render(recusa=RECUSA, contexto=contexto, pergunta=pergunta)
    return clean_text(client.complete(system, user, prompt=prompt)).strip()


def normalize_question(question: str) -> str:
    """Junta espaços, valida o tamanho e tira as tags que delimitam a pergunta no prompt."""
    # Sem as tags, um texto como "</pergunta> nova regra" não fecha o bloco antes da hora.
    pergunta = " ".join(_TAG_PERGUNTA.sub(" ", question).split())
    if not pergunta:
        raise ValueError("a pergunta está vazia")
    if len(pergunta) > MAX_PERGUNTA:
        raise ValueError(f"a pergunta tem {len(pergunta)} caracteres; o limite é {MAX_PERGUNTA}")
    return pergunta


def build_qa_context(solution: Solution, inst: Instance) -> dict[str, Any]:
    """Contexto completo do plano: os dados do relatório + as paradas de cada rota."""
    dados = build_report_data([solution], inst, "diario")
    rotas_ctx = {ctx.vehicle_id: ctx for ctx in build_route_contexts(solution, inst)}

    rotas = []
    for resumo in dados["rotas"]:
        ctx = rotas_ctx[resumo["veiculo"]]
        paradas = []
        for p in ctx.paradas:
            parada = {
                "ordem": p.ordem,
                "id": p.id,
                "nome": p.nome,
                "prioridade": PRIORIDADE_ROTULO[p.prioridade],
                "peso_kg": round(p.peso_kg, 1),
                "volume_l": round(p.volume_l, 1),
                "refrigerado": p.refrigerado,
            }
            if p.deadline_min is not None:
                parada["deadline_min"] = round(p.deadline_min)
            paradas.append(parada)
        rotas.append(
            {
                **resumo,
                "carga_kg": round(ctx.carga_kg, 1),
                "carga_l": round(ctx.carga_l, 1),
                "paradas": paradas,
            }
        )

    atendidas = {p["id"] for rota in rotas for p in rota["paradas"]}
    return {
        "instancia": dados["instancia"],
        "solucao": dados["plano_adotado"],
        "rotas": rotas,
        "entregas_nao_atendidas": [
            {"id": d.id, "nome": d.nome} for d in inst.deliveries if d.id not in atendidas
        ],
        "observacoes": dados["padroes"],
    }
