"""Configuração da frota (YAML) -> lista de Vehicle do domínio + parâmetros globais."""
from __future__ import annotations

from dataclasses import dataclass, field

from medroute.domain.models import Delivery, Priority, Vehicle


@dataclass(frozen=True)
class FleetConfig:
    vehicles: tuple[Vehicle, ...]
    fator_tortuosidade: float = 1.30
    jornada_max_min: float = 480.0
    inicio_jornada: str = "07:00"
    volumoso_limiar_l: float = 60.0
    servico_min_padrao: float = 10.0
    tipos_sem_volumoso: frozenset[str] = frozenset()
    transito: tuple = ()
    penalidade_prioridade: dict = field(default_factory=dict)

    def aceita(self, v: Vehicle, d: Delivery) -> bool:
        """Compatibilidade carga x veículo (refrigerado, volumoso, peso, volume)."""
        if d.refrigerado and not v.aceita_refrigerado:
            return False
        if d.volume_l > self.volumoso_limiar_l and v.tipo.value in self.tipos_sem_volumoso:
            return False
        return d.peso_kg <= v.capacidade_kg and d.volume_l <= v.capacidade_l

    def penalidade(self, p: Priority) -> float:
        return float(self.penalidade_prioridade.get(p.value, 0.0))
