"""Instruções de rota por motorista (Spec 05, P0)."""

from __future__ import annotations

import logging

from medroute.data.fleet import FleetConfig
from medroute.domain.models import Instance, Solution

from .client import LLMClient
from .context import PRIORIDADE_ROTULO, RouteContext, build_route_contexts
from .prompts import load_prompt
from .text import clean_text, numero_br

logger = logging.getLogger(__name__)

PROMPT = "instrucoes_motorista"
TENTATIVAS = 2  # a primeira + uma nova tentativa se a fidelidade falhar

# Anexado ao prompt na nova tentativa: orienta a correção e muda a chave do cache,
# que de outra forma devolveria a mesma resposta infiel.
AVISO_NOVA_TENTATIVA = (
    "ATENÇÃO: a resposta anterior omitiu ou reordenou paradas ou horários. Liste TODAS as "
    'paradas, na ordem do campo "ordem", com o nome exatamente como no campo "nome" e, '
    'logo depois do nome, o horário exatamente como no campo "chegada" (quando houver).'
)


def generate_instructions(
    solution: Solution,
    inst: Instance,
    client: LLMClient,
    fleet: FleetConfig | None = None,
) -> dict[str, str]:
    """Devolve vehicle_id -> instruções em Markdown, uma chamada à LLM por rota usada.

    Com `fleet`, as instruções trazem o horário previsto de chegada a cada parada."""
    prompt = load_prompt(PROMPT)
    instrucoes = {}
    for ctx in build_route_contexts(solution, inst, fleet):
        system, user = prompt.render(contexto=ctx.to_prompt_json())
        for tentativa in range(TENTATIVAS):
            mensagem = user if tentativa == 0 else f"{user}\n\n{AVISO_NOVA_TENTATIVA}"
            texto = clean_text(client.complete(system, mensagem, prompt=prompt))
            if is_faithful(texto, ctx):
                break
        else:
            logger.warning(
                "%s: resposta da LLM (%s/%s) omitiu ou reordenou paradas ou horários; "
                "usando o texto padrão",
                ctx.vehicle_id,
                client.provider,
                client.model,
            )
            texto = fallback_instructions(ctx)
        instrucoes[ctx.vehicle_id] = texto
    return instrucoes


def is_faithful(texto: str, ctx: RouteContext, *, horarios: bool = True) -> bool:
    """True se o nome de cada parada aparece no texto, na ordem da rota.

    Com `horarios`, cada nome precisa vir seguido do seu horário de chegada ("07:42"),
    antes do nome da parada seguinte; paradas sem horário só conferem o nome."""
    trechos = []
    for parada in ctx.paradas:
        trechos.append(parada.nome)
        chegada = ctx.horario(parada.chegada_min)
        if horarios and chegada:
            trechos.append(chegada)

    texto = _comparavel(texto)
    posicao = 0
    for trecho in map(_comparavel, trechos):
        encontrado = texto.find(trecho, posicao)
        if encontrado < 0:
            return False
        posicao = encontrado + len(trecho)
    return True


def _comparavel(texto: str) -> str:
    return " ".join(clean_text(texto).casefold().split())


def fallback_instructions(ctx: RouteContext) -> str:
    """Texto determinístico, sem LLM, usado quando a resposta não é fiel à rota."""
    saida = f" às {ctx.horario(0)}" if ctx.saida_min is not None else ""
    linhas = [
        f"### Rota {ctx.vehicle_id} ({ctx.vehicle_tipo.value})",
        f"Saída de {ctx.deposito}{saida}: {len(ctx.paradas)} paradas, "
        f"{numero_br(ctx.distancia_km)} km, cerca de {ctx.duracao_min:.0f} min, "
        f"carga de {numero_br(ctx.carga_kg)} kg / {numero_br(ctx.carga_l)} L.",
        "",
    ]
    alertas = ctx.alertas()
    if alertas:
        linhas += ["**Atenção**", *(f"- {a}" for a in alertas), ""]
    linhas.append("**Paradas**")
    for p in ctx.paradas:
        chegada = ctx.horario(p.chegada_min)
        horario = f" — chegada prevista às {chegada}" if chegada else ""
        cuidados = ", refrigerado" if p.refrigerado else ""
        linhas.append(
            f"{p.ordem}. {p.nome}{horario} — prioridade {PRIORIDADE_ROTULO[p.prioridade]}, "
            f"{numero_br(p.peso_kg)} kg / {numero_br(p.volume_l)} L{cuidados}"
        )
    retorno = ctx.horario(ctx.duracao_min)
    previsao = f", com chegada prevista às {retorno}" if retorno else ""
    linhas += ["", f"**Retorno:** volte ao depósito {ctx.deposito} ao final{previsao}."]
    return "\n".join(linhas)
