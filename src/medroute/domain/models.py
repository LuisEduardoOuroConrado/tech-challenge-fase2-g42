"""Modelos de domínio compartilhados entre os módulos do medroute."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositiveFloat = Annotated[float, Field(gt=0)]


class DomainModel(BaseModel):
    """Configuração comum para os contratos públicos do domínio."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class Priority(StrEnum):
    CRITICA = "critica"
    ALTA = "alta"
    NORMAL = "normal"


class VehicleType(StrEnum):
    MOTO = "moto"
    CARRO = "carro"
    VAN = "van"


class Depot(DomainModel):
    id: Identifier
    nome: Identifier
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class Delivery(DomainModel):
    id: Identifier
    nome: Identifier
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    peso_kg: NonNegativeFloat
    volume_l: NonNegativeFloat
    prioridade: Priority
    refrigerado: bool = False
    deadline_min: PositiveFloat | None = None

    @model_validator(mode="after")
    def deadline_apenas_para_entrega_critica(self) -> Self:
        if self.deadline_min is not None and self.prioridade is not Priority.CRITICA:
            raise ValueError("deadline_min só pode ser definido para entrega crítica")
        return self


class Vehicle(DomainModel):
    id: Identifier
    tipo: VehicleType
    capacidade_kg: PositiveFloat
    capacidade_l: PositiveFloat
    autonomia_km: PositiveFloat
    velocidade_kmh: PositiveFloat
    custo_km: NonNegativeFloat
    custo_fixo: NonNegativeFloat
    aceita_refrigerado: bool = True


class Instance(DomainModel):
    nome: Identifier
    depot: Depot
    deliveries: Annotated[list[Delivery], Field(min_length=1)]
    fleet: Annotated[list[Vehicle], Field(min_length=1)]

    @model_validator(mode="after")
    def ids_devem_ser_unicos(self) -> Self:
        delivery_ids = [delivery.id for delivery in self.deliveries]
        if len(delivery_ids) != len(set(delivery_ids)):
            raise ValueError("os ids das entregas devem ser únicos")
        if self.depot.id in delivery_ids:
            raise ValueError("o id do depósito não pode ser usado por uma entrega")

        vehicle_ids = [vehicle.id for vehicle in self.fleet]
        if len(vehicle_ids) != len(set(vehicle_ids)):
            raise ValueError("os ids dos veículos devem ser únicos")
        return self


class Route(DomainModel):
    vehicle_id: Identifier
    sequence: list[Identifier]
    distancia_km: NonNegativeFloat
    duracao_min: NonNegativeFloat
    carga_kg: NonNegativeFloat
    carga_l: NonNegativeFloat
    custo: NonNegativeFloat
    violacoes: dict[Identifier, NonNegativeFloat] = Field(default_factory=dict)

    @model_validator(mode="after")
    def entregas_nao_podem_se_repetir(self) -> Self:
        if len(self.sequence) != len(set(self.sequence)):
            raise ValueError("uma rota não pode conter entregas repetidas")
        return self


class Solution(DomainModel):
    instance_nome: Identifier
    algoritmo: Identifier
    routes: list[Route]
    fitness: NonNegativeFloat
    custo_operacional: NonNegativeFloat
    distancia_total_km: NonNegativeFloat
    penalidades: dict[Identifier, NonNegativeFloat] = Field(default_factory=dict)
    historico_fitness: list[NonNegativeFloat] = Field(default_factory=list)
    tempo_exec_s: NonNegativeFloat
    seed: int

    @model_validator(mode="after")
    def rotas_e_entregas_devem_ser_unicas(self) -> Self:
        vehicle_ids = [route.vehicle_id for route in self.routes]
        if len(vehicle_ids) != len(set(vehicle_ids)):
            raise ValueError("cada veículo pode aparecer em apenas uma rota")

        delivery_ids = [
            delivery_id
            for route in self.routes
            for delivery_id in route.sequence
        ]
        if len(delivery_ids) != len(set(delivery_ids)):
            raise ValueError("uma entrega pode aparecer em apenas uma rota")
        return self
