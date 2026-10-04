# Spec 03 — Função de avaliação (fitness) e restrições

**Autores:** Conrado e Beatriz · **Revisor:** a definir (1 aprovação) · **Status:** RASCUNHO para discussão
**Base:** ADR 0004 (custo generalizado em R$, sem Pareto/NSGA-II) e `domain/models.py`.

## 1. Ideia em uma frase
O algoritmo genético compara soluções por **um único número em reais** (o *fitness*): quanto menor, melhor. Rota que viola regra não é proibida, mas **sai tão cara** que o algoritmo aprende a evitá-la.

## 2. Fórmula

```
fitness = custo_operacional + custo_prioridade + penalidades
```

| Termo | Como calcula | Quem implementa |
|---|---|---|
| `custo_operacional` | por veículo **usado**: `custo_fixo + custo_km × distância_km`. Veículo sem entregas não paga o fixo. | Conrado |
| `custo_prioridade` | para cada entrega: `peso_da_prioridade (R$/min) × minutos até a chegada` (crítica 5,0 · alta 1,5 · normal 0,2; valores em `configs/frota.yaml`). Faz entregas críticas virem primeiro. | Beatriz (cálculo) / Conrado (soma) |
| `penalidades` | soma, por tipo de violação, de `quantidade_violada × peso_R$` (seção 3) | Beatriz (violações) / Conrado (pesos e soma) |

Coerência com a fixture `solution_sp15.json`: `custo_operacional` = soma de `custo` das rotas; `fitness − custo_operacional − penalidades` = custo de prioridade.

## 3. Violações (funções puras, sem efeito colateral, testadas) — Beatriz

Cada função recebe dados do domínio e devolve um número ≥ 0 (**0 = sem violação**). Chaves iguais às de `Route.violacoes`.

| Chave | O que mede (unidade) | Camada |
|---|---|---|
| `capacidade` | excesso de carga: `max(0, kg/cap_kg − 1) + max(0, L/cap_L − 1)` (fração) | P0 |
| `autonomia` | km acima da autonomia do veículo | P0 |
| `compatibilidade` | nº de entregas que o veículo não pode levar (refrigerado, volumoso) — via `FleetConfig.aceita` | P1 |
| `deadline` | soma dos minutos de atraso das entregas críticas | P1 |
| `jornada` | minutos acima de 480 (8 h) | P1 |

Funções propostas (módulo `src/medroute/constraints/`):

```python
violacao_capacidade(veiculo, entregas) -> float
violacao_autonomia(veiculo, km) -> float
violacao_compatibilidade(fleet, veiculo, entregas) -> float
violacao_deadline(chegadas_min, entregas) -> float
violacao_jornada(duracao_min, fleet) -> float
custo_prioridade(chegadas_min, entregas, fleet) -> float
cronograma_rota(dm, veiculo, rota, instance, fleet, saida_min=None) -> dict[id, float]  # minuto de chegada
```

`cronograma_rota` usa `DistanceMatrix.time()` + tempo de parada (`servico_min_padrao`). Sem `saida_min` não há fator de trânsito (P0); com ele aplica o fator por período (P1).

## 4. Pesos das penalidades (PROPOSTA — Conrado calibra)

Princípio: **violar nunca pode compensar** (o maior custo fixo é R$ 200).

| Violação | Peso sugerido |
|---|---|
| capacidade | R$ 2.000 por 100% de excesso |
| autonomia | R$ 20 por km |
| compatibilidade | R$ 1.000 por entrega |
| deadline | R$ 10 por minuto (somado ao custo de prioridade) |
| jornada | R$ 5 por minuto |

Os pesos ficam em arquivo de configuração (não no código) para o experimento E5 (sensibilidade) poder variá-los.

## 5. Contrato com o motor do GA — Conrado
- O decodificador (sequência única → rotas por veículo) chama, para cada rota: distância → violações → custo e monta `Route` e `Solution` do `models.py`.
- Mesma entrada ⇒ mesmo fitness (determinístico, sem sorteio dentro da avaliação).
- Todas as entregas aparecem exatamente uma vez na solução; entrega faltando é erro, não penalidade.

## 6. Decisões em aberto
1. `custo_prioridade` pesa o **tempo até a chegada** (minha leitura do ADR 0004) ou só o **atraso** além de um prazo?
2. Violação de capacidade soma kg e litros ou usa só o maior excesso?
3. Os pesos da seção 4 servem como ponto de partida?
4. `servico_min` e `aceita_volumoso` entram no `models.py` (ver spec 01)?
5. Em P0 o `custo_prioridade` usa tempo sem trânsito, certo?

## 7. Prazos (do cronograma)
- 14/10: violações P0 (capacidade, autonomia, prioridade) — Beatriz
- 16/10: decodificador + fitness P0 funcionando em `sp_40` — Conrado
- 21/10: violações P1 + fator de trânsito (Beatriz); fitness P1 (Conrado)
