# Spec 01 — Domínio e dados (Beatriz · revisor: Conrado)

**Status:** Aprovada em 05/10/2026 (revisor: Conrado · autora: Beatriz) · **Escopo:** `src/medroute/data/`, `configs/frota.yaml`, `data/instances/`

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

## Critérios de aceite
1. **Dado** o mesmo `nome`, `n_total`, `n_real` e `seed`, **quando** `generate_instance` roda duas vezes, **então** as instâncias são iguais; com outra seed, diferem.
2. **Dada** uma instância gerada com `n` entregas, **quando** ela é validada, **então** tem `round(0,15·n)` críticas, `round(0,25·n)` altas, ≥10% refrigeradas, todas as entregas a ≤15 km do depósito e `deadline_min` definido exatamente nas críticas.
3. **Dada** uma instância com crítica sem prazo, peso/volume ≤ 0, entrega que nenhum veículo atende ou peso total acima da frota, **quando** `load_instance`/`validate_instance` roda, **então** levanta `DataError` com todos os erros agregados.
4. **Dado** um `frota.yaml` válido, **quando** `load_fleet` roda, **então** devolve os 5 veículos na ordem `moto-01, moto-02, carro-01, carro-02, van-01`; quantidade ≤ 0 ou campo ausente gera `DataError`.
5. **Dada** uma moto, **quando** a entrega é refrigerada ou volumosa (> 60 L), **então** `FleetConfig.aceita` devolve `False`; carro e van aceitam.
6. **Dada** uma instância, **quando** a `DistanceMatrix` é construída, **então** a matriz é `(n+1)×(n+1)`, simétrica, com diagonal zero, respeita a desigualdade triangular e vale haversine × 1,30.
7. **Dada** uma rota sem o depósito, **quando** `route_km` é chamado, **então** inclui a saída e o retorno ao depósito; rota vazia vale 0.
8. **Dado** `time(i, j, vel)` sem `saida_min`, **então** não há fator de trânsito (P0); com `saida_min` aplica o fator do período (P1); velocidade ≤ 0 gera `ValueError`.
9. **Dada** uma instância salva com `save_instance`, **quando** é lida com `load_instance`, **então** é igual à original; as instâncias versionadas `sp_15/40/80` carregam sem erro.

## Testes obrigatórios (`tests/unit/data/test_data.py`)
| Critério | Teste |
|---|---|
| 1 | `test_gerador_deterministico` |
| 2 | `test_mix_e_raio` |
| 3 | `test_validacao_critica_sem_deadline`, `test_entrega_sem_veiculo_compativel`, `test_modelo_rejeita_deadline_em_nao_critica` |
| 4 | `test_frota_carrega`, `test_frota_invalida` |
| 5 | `test_compatibilidade_moto` |
| 6 | `test_matriz_propriedades`, `test_matriz_aplica_fator`, `test_haversine_conhecido` |
| 7 e 8 | `test_rota_km_e_tempo` |
| 9 | `test_roundtrip_json`, `test_instancias_commitadas_carregam` |

Lacunas a cobrir (não bloqueiam a aprovação): `test_mix_e_raio` checa ≥1 refrigerada em vez de ≥10%; faltam testes para peso/volume ≤ 0 e para peso total acima da capacidade da frota.

## Pedidos ao Conrado (models.py) — respondidos na revisão
- **`servico_min` e `aceita_volumoso`: não entram no `models.py`**, que segue congelado. O tempo de parada fica fixo em `servico_min_padrao` (YAML) e o volumoso em `FleetConfig.tipos_sem_volumoso`/`FleetConfig.aceita`. Consequência: no P1, o fitness/decoder do GA recebe o `FleetConfig` para checar volumoso e somar tempo de parada (Spec 03).
- **`Instance` sem `seed`: ok.** A seed fica no CLI (`medroute gen --seed`, padrão 42) e no README.
- **`Vehicle.aceita_refrigerado` com default `True`: ok**, desde que o YAML declare `false` explicitamente para a moto (já declara e há teste).

## Fora desta spec / pendências
- Fontes dos números da frota (C2): entrego no PR até 07/10.
- Coordenadas reais aproximadas: conferir (CNES/Maps) até 07/10; itens "(ref.)" são UBS de referência a confirmar.
- `sp_40` e `sp_80` já gerados (seed 42); sp_40 oficial entra no prazo de 07/10 após conferência das coordenadas.
