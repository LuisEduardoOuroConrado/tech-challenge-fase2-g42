# Spec 01 — Domínio e dados (Beatriz · revisor: Conrado)

**Escopo:** o que a camada de dados entrega aos demais módulos. Os tipos são os de `domain/models.py` (Conrado, congelado 30/09), usados sem alteração; a camada de dados não define tipos próprios.

## Interfaces
| Função / classe | Contrato |
|---|---|
| `load_fleet(path) -> FleetConfig` | Lê `configs/frota.yaml`; `FleetConfig.vehicles` = 5 `Vehicle` (`moto-01`, `moto-02`, `carro-01`, `carro-02`, `van-01`) + parâmetros globais. `FleetConfig.aceita(veiculo, entrega)` = compatibilidade carga×veículo. |
| `load_instance(path, fleet) -> Instance` | Lê JSON e **valida**: regras do próprio modelo (ids únicos, deadline só p/ crítica) + crítica com `deadline_min`, peso/volume > 0, cada entrega atendível por ≥1 veículo, peso total ≤ capacidade da frota. Erros agregados em `DataError`. |
| `generate_instance(nome, n_total, n_real, seed)` | Determinística. Depósito = Farmácia Central HC-FMUSP. Mix por **quota exata**: 15% críticas, 25% altas, resto normais; ≥10% refrigeradas; domicílios em raio 15 km. |
| `DistanceMatrix(inst, fleet)` | Índice 0 = depósito, i = posição da entrega em `inst.deliveries` + 1. `km(i,j)`, `matrix()`, `route_km(rota)`, `time(i,j,vel_kmh,saida_min=None)`. |

## Decisões
- Distância = haversine × `fator_tortuosidade` (1,30; ADR 0003). Simétrica, offline.
- `time()` sem `saida_min` = P0 (sem trânsito). Com `saida_min` aplica fator por período (P1: 06–09 ×1,4; 09–17 ×1,0; 17–20 ×1,5).
- Item é "volumoso" se volume > 60 L (moto não leva). Refrigerado: moto não leva.
- `deadline_min` = minutos desde o início da jornada (07:00), só para críticas.

## Pedidos ao Conrado (models.py)
- Faltam `servico_min` (tempo de parada) em `Delivery` e `aceita_volumoso` em `Vehicle`. Por ora: tempo de parada fixo em `servico_min_padrao` (YAML) e volumoso tratado por `FleetConfig.tipos_sem_volumoso`.
- `Instance` não tem `seed`; a seed fica documentada no CLI (42) e no README.
- `Vehicle.aceita_refrigerado` tem default `True`; no YAML a moto é `false` explicitamente.

## Fora desta spec / pendências
- Fontes dos números da frota (C2): entrego no PR até 07/10.
- Coordenadas reais aproximadas: conferir (CNES/Maps) até 07/10; itens "(ref.)" são UBS de referência a confirmar.
- `sp_40` e `sp_80` já gerados (seed 42); sp_40 oficial entra no prazo de 07/10 após conferência das coordenadas.
