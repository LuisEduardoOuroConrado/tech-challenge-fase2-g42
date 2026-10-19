"""Configuração da frota (YAML) -> lista de Vehicle do domínio + parâmetros globais."""
from __future__ import annotations

from dataclasses import dataclass

from medroute.domain.models import Delivery, Vehicle


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

    @property
    def saida_min(self) -> float | None:
        """Minuto do dia em que as rotas saem do depósito (`inicio_jornada`).

        Todas as rotas saem juntas no início da jornada. Sem faixas de `transito` no YAML devolve
        None, e o tempo de viagem fica sem fator de trânsito (P0)."""
        if not self.transito:
            return None
        h, m = self.inicio_jornada.split(":")
        return int(h) * 60 + int(m)

    def compativel(self, v: Vehicle, d: Delivery) -> bool:
        """Só a compatibilidade da carga (refrigerado, volumoso); não olha capacidade."""
        if d.refrigerado and not v.aceita_refrigerado:
            return False
        return not (d.volume_l > self.volumoso_limiar_l and v.tipo.value in self.tipos_sem_volumoso)

    def aceita(self, v: Vehicle, d: Delivery) -> bool:
        """Compatibilidade + a entrega sozinha cabe no veículo (peso e volume)."""
        cabe = d.peso_kg <= v.capacidade_kg and d.volume_l <= v.capacidade_l
        return self.compativel(v, d) and cabe
