"""Junção determinística de `Solution` + `Instance` no contexto enviado à LLM (Spec 05).

Todos os fatos que a LLM usa (ordem, nomes, cargas, distâncias, horários, alertas) saem
daqui; a LLM apenas redige o texto.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from medroute.constraints import cronograma_rota, duracao_rota
from medroute.data.distance import DistanceMatrix
from medroute.data.fleet import FleetConfig
from medroute.domain.models import Instance, Priority, Solution, VehicleType

from .text import hora, numero_br

PRIORIDADE_ROTULO = {Priority.CRITICA: "crítica", Priority.ALTA: "alta", Priority.NORMAL: "normal"}


class _Context(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StopContext(_Context):
    ordem: int
    id: str
    nome: str
    prioridade: Priority
    peso_kg: float
    volume_l: float
    refrigerado: bool
    deadline_min: float | None
    chegada_min: float | None = None  # minutos após a saída, antes do atendimento


class RouteContext(_Context):
    vehicle_id: str
    vehicle_tipo: VehicleType
    deposito: str
    paradas: list[StopContext]
    distancia_km: float
    duracao_min: float
    carga_kg: float
    carga_l: float
    custo: float
    violacoes: dict[str, float]  # apenas as maiores que zero
    saida_min: float | None = None  # minuto do dia da saída (420 = 07:00); None = sem horários

    def horario(self, minutos_apos_saida: float | None) -> str | None:
        """'HH:MM' de um instante da rota; None sem horário de saída."""
        if self.saida_min is None or minutos_apos_saida is None:
            return None
        return hora(self.saida_min + minutos_apos_saida)

    def alertas(self) -> list[str]:
        alertas = []
        for p in self.paradas:
            if p.prioridade is Priority.CRITICA:
                prazo = ""
                if p.deadline_min:
                    prazo = f", prazo de {p.deadline_min:.0f} min após a saída"
                    if limite := self.horario(p.deadline_min):
                        prazo += f" (até {limite})"
                alertas.append(f"Parada {p.ordem} ({p.nome}): entrega CRÍTICA{prazo}")
            if p.refrigerado:
                alertas.append(f"Parada {p.ordem} ({p.nome}): carga REFRIGERADA")
        for tipo, valor in self.violacoes.items():
            alertas.append(f"Violação de {tipo}: {numero_br(valor)} acima do limite")
        return alertas

    def to_prompt_json(self) -> str:
        """JSON compacto e arredondado para o prompt (economiza tokens)."""
        paradas = []
        for p in self.paradas:
            parada = {
                "ordem": p.ordem,
                "nome": p.nome,
                "prioridade": PRIORIDADE_ROTULO[p.prioridade],
                "peso_kg": round(p.peso_kg, 1),
                "volume_l": round(p.volume_l, 1),
                "refrigerado": p.refrigerado,
            }
            if chegada := self.horario(p.chegada_min):
                parada["chegada"] = chegada
            if p.deadline_min is not None:
                parada["deadline_min"] = round(p.deadline_min)
            paradas.append(parada)
        resumo: dict[str, object] = {"paradas": len(self.paradas)}
        if self.saida_min is not None:
            resumo["saida"] = self.horario(0)
            resumo["retorno"] = self.horario(self.duracao_min)
        resumo |= {
            "distancia_km": round(self.distancia_km, 1),
            "duracao_min": round(self.duracao_min),
            "carga_kg": round(self.carga_kg, 1),
            "carga_l": round(self.carga_l, 1),
        }
        dados = {
            "veiculo": {"id": self.vehicle_id, "tipo": self.vehicle_tipo.value},
            "deposito": self.deposito,
            "resumo": resumo,
            "paradas": paradas,
            "alertas": self.alertas(),
        }
        return json.dumps(dados, ensure_ascii=False, separators=(",", ":"))


def build_route_contexts(
    solution: Solution, inst: Instance, fleet: FleetConfig | None = None
) -> list[RouteContext]:
    """Com `fleet`, cada parada ganha o horário de chegada previsto (`cronograma_rota`, com
    saída em `inicio_jornada` e o fator de trânsito, como no GA); sem ela, não há horários."""
    if solution.instance_nome != inst.nome:
        raise ValueError(
            f"a solução é da instância {solution.instance_nome!r}, não de {inst.nome!r}"
        )
    entregas = {d.id: d for d in inst.deliveries}
    veiculos = {v.id: v for v in inst.fleet}
    dm = DistanceMatrix(inst, fleet) if fleet is not None else None

    contexts = []
    for route in solution.routes:
        if not route.sequence:
            continue  # veículo não usado
        veiculo = veiculos.get(route.vehicle_id)
        if veiculo is None:
            raise ValueError(f"veículo {route.vehicle_id!r} não existe na instância {inst.nome!r}")

        faltando = [i for i in route.sequence if i not in entregas]
        if faltando:
            raise ValueError(f"entrega {faltando[0]!r} não existe na instância {inst.nome!r}")
        chegadas, duracao = {}, route.duracao_min
        if dm is not None:
            # A duração sai do mesmo cronograma, para o retorno não vir antes da última parada.
            args = (dm, veiculo, route.sequence, inst, fleet, fleet.saida_min)
            chegadas, duracao = cronograma_rota(*args), duracao_rota(*args)

        paradas = []
        for ordem, delivery_id in enumerate(route.sequence, start=1):
            d = entregas[delivery_id]
            paradas.append(
                StopContext(
                    ordem=ordem,
                    id=d.id,
                    nome=d.nome,
                    prioridade=d.prioridade,
                    peso_kg=d.peso_kg,
                    volume_l=d.volume_l,
                    refrigerado=d.refrigerado,
                    deadline_min=d.deadline_min,
                    chegada_min=chegadas.get(d.id),
                )
            )

        contexts.append(
            RouteContext(
                vehicle_id=veiculo.id,
                vehicle_tipo=veiculo.tipo,
                deposito=inst.depot.nome,
                paradas=paradas,
                distancia_km=route.distancia_km,
                duracao_min=duracao,
                carga_kg=route.carga_kg,
                carga_l=route.carga_l,
                custo=route.custo,
                violacoes={k: v for k, v in route.violacoes.items() if v > 0},
                saida_min=dm.inicio_jornada_min if dm is not None else None,
            )
        )
    return contexts
