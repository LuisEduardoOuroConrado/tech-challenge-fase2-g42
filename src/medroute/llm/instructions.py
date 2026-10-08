"""Instruções de rota por motorista (Spec 05, P0)."""

from __future__ import annotations

import logging

from medroute.domain.models import Instance, Solution

from .client import LLMClient
from .context import PRIORIDADE_ROTULO, RouteContext, build_route_contexts, numero_br
from .prompts import load_prompt

logger = logging.getLogger(__name__)

PROMPT = "instrucoes_motorista"
TENTATIVAS = 2  # a primeira + uma nova tentativa se a fidelidade falhar


def generate_instructions(
    solution: Solution,
    inst: Instance,
    client: LLMClient,
) -> dict[str, str]:
    """Devolve vehicle_id -> instruções em Markdown, uma chamada à LLM por rota usada."""
    prompt = load_prompt(PROMPT)
    instrucoes = {}
    for ctx in build_route_contexts(solution, inst):
        system, user = prompt.render(contexto=ctx.to_prompt_json())
        for _ in range(TENTATIVAS):
            texto = client.complete(system, user)
            if is_faithful(texto, ctx):
                break
        else:
            logger.warning(
                "%s: resposta da LLM (%s/%s) omitiu ou reordenou paradas; usando o texto padrão",
                ctx.vehicle_id,
                client.provider,
                client.model,
            )
            texto = fallback_instructions(ctx)
        instrucoes[ctx.vehicle_id] = texto
    return instrucoes


def is_faithful(texto: str, ctx: RouteContext) -> bool:
    """True se o nome de cada parada aparece no texto, na ordem da rota."""
    texto = texto.casefold()
    posicao = 0
    for parada in ctx.paradas:
        encontrado = texto.find(parada.nome.casefold(), posicao)
        if encontrado < 0:
            return False
        posicao = encontrado + len(parada.nome)
    return True


def fallback_instructions(ctx: RouteContext) -> str:
    """Texto determinístico, sem LLM, usado quando a resposta não é fiel à rota."""
    linhas = [
        f"### Rota {ctx.vehicle_id} ({ctx.vehicle_tipo.value})",
        f"Saída de {ctx.deposito}: {len(ctx.paradas)} paradas, "
        f"{numero_br(ctx.distancia_km)} km, cerca de {ctx.duracao_min:.0f} min, "
        f"carga de {numero_br(ctx.carga_kg)} kg / {numero_br(ctx.carga_l)} L.",
        "",
    ]
    alertas = ctx.alertas()
    if alertas:
        linhas += ["**Atenção**", *(f"- {a}" for a in alertas), ""]
    linhas.append("**Paradas**")
    for p in ctx.paradas:
        cuidados = ", refrigerado" if p.refrigerado else ""
        linhas.append(
            f"{p.ordem}. {p.nome} — prioridade {PRIORIDADE_ROTULO[p.prioridade]}, "
            f"{numero_br(p.peso_kg)} kg / {numero_br(p.volume_l)} L{cuidados}"
        )
    linhas += ["", f"**Retorno:** volte ao depósito {ctx.deposito} ao final."]
    return "\n".join(linhas)
