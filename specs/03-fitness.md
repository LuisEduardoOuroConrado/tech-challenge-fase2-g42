# Spec 03 — Função de avaliação (fitness) e restrições

**Autores:** Conrado e Beatriz · **Revisor:** Conrado (revisão 05/10/2026) · **Status:** Aprovada em 05/10/2026 (OK da Beatriz)
**Base:** ADR 0004 (custo generalizado em R$, sem Pareto/NSGA-II), `domain/models.py` e Spec 01.

## 1. Ideia em uma frase
O algoritmo genético compara soluções por **um único número em reais** (o *fitness*): quanto menor, melhor. Rota que viola regra não é proibida, mas **sai tão cara** que o algoritmo aprende a evitá-la.

## 2. Fórmula

```
fitness = custo_operacional + custo_prioridade + penalidades
```

| Termo | Como calcula | Quem implementa |
|---|---|---|
| `custo_operacional` | por veículo **usado**: `custo_fixo + custo_km × distância_km` (ida e volta ao depósito). Veículo sem entregas não paga o fixo. | Conrado (já no decoder) |
| `custo_prioridade` | Σ entregas `peso_da_prioridade (R$/min) × minuto de chegada` desde a saída do depósito. Faz entregas críticas virem primeiro e torna vantajoso usar mais de um veículo. | Beatriz (cálculo) / Conrado (soma) |
| `penalidades` | Σ por tipo de violação: `fixo × [violação > 0] + unitário × quantidade_violada` (seção 4) | Beatriz (violações) / Conrado (pesos e soma) |

Coerência com a fixture `solution_sp15.json`: `custo_operacional` = soma de `custo` das rotas; `Solution.penalidades` = R$ por tipo de violação; `fitness − custo_operacional − Σ penalidades` = custo de prioridade.

## 3. Violações (funções puras, sem efeito colateral, testadas) — Beatriz

Cada função recebe dados do domínio e devolve um número ≥ 0 (**0 = sem violação**). Chaves iguais às de `Route.violacoes`.

| Chave | O que mede (unidade) | Tipo | Camada |
|---|---|---|---|
| `capacidade` | excesso de carga: `max(0, kg/cap_kg − 1) + max(0, L/cap_L − 1)` (fração somada) | hard | P0 |
| `autonomia` | km acima da autonomia do veículo | hard | P0 |
| `compatibilidade` | nº de entregas que o veículo não pode levar, via `FleetConfig.aceita` (refrigerado já checado no decoder em P0; volumoso entra em P1) | hard | P0/P1 |
| `deadline` | soma dos minutos de atraso das entregas críticas (`chegada − deadline_min`) | soft | P1 |
| `jornada` | minutos acima de `jornada_max_min` (480), contando viagem + paradas | soft | P1 |

Funções (módulo `src/medroute/constraints/`):

```python
violacao_capacidade(veiculo, entregas) -> float
violacao_autonomia(veiculo, km) -> float
violacao_compatibilidade(fleet, veiculo, entregas) -> float
violacao_deadline(chegadas_min, entregas) -> float
violacao_jornada(duracao_min, fleet) -> float
custo_prioridade(chegadas_min, entregas, pesos) -> float   # pesos: dict[Priority, float] do fitness.yaml
cronograma_rota(dm, veiculo, rota, instance, fleet, saida_min=None) -> dict[id, float]  # minuto de chegada
```

`cronograma_rota` usa `DistanceMatrix.time()` + `FleetConfig.servico_min_padrao` (10 min) por parada; a chegada é o minuto em que o veículo chega à entrega, antes do atendimento. Sem `saida_min` não há fator de trânsito (P0); com ele aplica o fator por período (P1).

## 4. Pesos — `configs/fitness.yaml`

Todos os pesos ficam em `configs/fitness.yaml` (ADR 0004), não no código, para o experimento E5 (sensibilidade) poder variá-los.

**Prioridade (R$ por minuto até a chegada):** crítica **0,50** · alta **0,15** · normal **0,05** (R$ 30, 9 e 3 por hora; proporção 10 : 3 : 1 do planejamento).

Calibração em `sp_40` (GA atual, seed 7; minutos de chegada somados por prioridade):

| Cenário | Custo operacional | Σ chegada crít. / alta / normal | Prioridade com 5,0/1,5/0,2 | Prioridade com 0,50/0,15/0,05 |
|---|---|---|---|---|
| 1 van (solução atual do GA) | R$ 621 | 3.185 / 3.373 / 10.855 min | R$ 23.156 | R$ 2.641 |
| 5 veículos (corte ingênuo) | R$ 890 | 568 / 729 / 2.166 min | R$ 4.367 | R$ 501 |

Com os pesos antigos a prioridade era ~37× o custo operacional e anulava a escolha de frota; com os novos fica na mesma ordem de grandeza, e usar mais veículos compensa só quando antecipa entregas de verdade.

**Penalidades:** `fixo` é cobrado uma vez por rota com violação > 0; `unitário` multiplica a quantidade violada.

| Violação | Fixo (R$/rota) | Unitário | Justificativa |
|---|---|---|---|
| capacidade | 1.000 | R$ 2.000 por 100% de excesso | hard: o fixo impede que um excesso pequeno saia mais barato que ativar outro veículo (R$ 60–200) |
| autonomia | 1.000 | R$ 20 por km | hard, mesmo motivo |
| compatibilidade | 0 | R$ 1.000 por entrega | hard e já discreta (≥ R$ 1.000 por ocorrência) |
| deadline | 0 | R$ 10 por minuto de atraso | soft (ADR 0001): somado ao custo de prioridade |
| jornada | 0 | R$ 5 por minuto acima de 8 h | soft |

Princípio: **violar uma restrição hard nunca compensa** — qualquer violação hard custa ≥ R$ 1.000, acima do maior custo fixo da frota (R$ 200).

A chave `penalidade_prioridade_rs_min` de `configs/frota.yaml` fica obsoleta: os pesos de prioridade passam a vir de `fitness.yaml` e a chave sai do `frota.yaml` quando `constraints/` entrar (Beatriz, 14/10).

## 5. Contrato com o motor do GA — Conrado

```python
# ga/fitness.py
class FitnessConfig(BaseModel): ...                       # espelha configs/fitness.yaml
def load_fitness_config(path="configs/fitness.yaml") -> FitnessConfig: ...
def make_fitness(inst, dm, fleet, cfg) -> Callable[[list[Route]], float]: ...  # vira GeneticAlgorithm(fitness_fn=...)
def penalties(routes, cfg) -> dict[str, float]: ...       # R$ por tipo, vai para Solution.penalidades
```

- O decoder (giant tour → rotas) chama, para cada rota: distância → cronograma → violações → custo e monta `Route`.
- Mesma entrada ⇒ mesmo fitness (determinístico, sem sorteio dentro da avaliação).
- Todas as entregas aparecem exatamente uma vez na solução; entrega faltando é erro (`ValueError`), não penalidade.
- Até `constraints/` existir, `ga/fitness.py` mantém a versão provisória (sem custo de prioridade), já com a mesma assinatura de `fitness_fn` (Spec 02).

## 6. Decisões (fechadas na revisão de 05/10/2026)
1. **`custo_prioridade` pesa o tempo até a chegada**, não só o atraso — é o que o ADR 0004 (aceito) define. O atraso além do prazo é cobrado à parte pela penalidade `deadline`.
2. **Capacidade soma** as frações de excesso em kg e em litros.
3. **Pesos:** os de penalidade da proposta original servem de base, com fixo de R$ 1.000 nas hard (seção 4); os de prioridade foram reduzidos 10× para 0,50 / 0,15 / 0,05 com base na calibração da seção 4.
4. **`servico_min` e `aceita_volumoso` não entram no `models.py`** (decidido na Spec 01): tempo de parada de `FleetConfig.servico_min_padrao`, volumoso via `FleetConfig.aceita`. O fitness recebe o `FleetConfig`.
5. **P0 usa tempo sem trânsito** (`saida_min=None`); o fator por período entra em P1.

## 7. Critérios de aceite
1. **Dada** uma solução sem violações, **quando** avaliada, **então** `fitness = custo_operacional + custo_prioridade` e `Solution.penalidades` soma 0.
2. **Dada** uma rota com excesso de capacidade de qualquer tamanho, **quando** avaliada, **então** paga pelo menos R$ 1.000 de penalidade (vale também para autonomia).
3. **Dadas** duas soluções iguais exceto pela ordem de uma entrega crítica e uma normal, **quando** avaliadas, **então** a que atende a crítica antes tem fitness menor.
4. **Dada** uma entrega crítica que chega `x` minutos depois do `deadline_min`, **quando** avaliada (P1), **então** a penalidade `deadline` vale `10 × x`.
5. **Dado** um veículo sem entregas, **quando** avaliado, **então** não paga custo fixo nem aparece nas rotas.
6. **Dada** a mesma entrada, **quando** avaliada duas vezes, **então** o fitness é idêntico.
7. **Dado** um `fitness.yaml` com pesos alterados, **quando** carregado, **então** o fitness muda conforme os novos pesos sem alteração de código.
8. **Dado** `cronograma_rota` sem `saida_min`, **então** a chegada em cada parada = Σ tempos de viagem + 10 min × paradas anteriores; com `saida_min` aplica o fator de trânsito do período.

## 8. Testes obrigatórios
- `constraints/` (Beatriz): cada violação com caso zero, caso positivo e caso-limite (exatamente na capacidade/autonomia/jornada); `custo_prioridade` com pesos diferentes por prioridade; `cronograma_rota` com e sem trânsito.
- `ga/fitness.py` (Conrado): critérios 1–7, incluindo a decomposição `fitness = custo_operacional + prioridade + Σ penalidades`, a leitura de `fitness.yaml` e erro claro para chave ausente.
- Integração: GA em `sp_40` com o fitness definitivo sem violação hard.

## 9. Prazos (do cronograma)
- 14/10: violações P0 (capacidade, autonomia, prioridade) + `cronograma_rota` — Beatriz
- 16/10: fitness P0 com `fitness.yaml` funcionando em `sp_40` — Conrado
- 21/10: violações P1 + fator de trânsito (Beatriz); fitness P1 (Conrado)
