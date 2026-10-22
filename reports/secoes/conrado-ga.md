# Algoritmo genético: do TSP ao VRP com frota heterogênea

**Autor:** Conrado (Parte A) · **Requisitos:** R1–R10 e R19 (seções "GA a partir do código base" e "estratégias
para as restrições") · **Base:** `docs/do-tsp-ao-vrp.md`, `docs/arquitetura.md`, Specs 02 e 03.

> **Rascunho de 22/10.** Os números são da rodada oficial de 19/10 (dados reais do PR #18 + fator de trânsito do
> PR #21, `main` `646db7a`). Se a frota mudar (`docs/fontes-frota.md` seção 2), as tabelas da seção 6 precisam
> ser refeitas. Os resultados do E1–E6 (Pedro) entram na seção comparativa, não aqui.

---

## 1. O problema

Um hospital distribui medicamentos e insumos a partir de um depósito (complexo do HC, São Paulo) para 15, 40 ou
80 pontos de entrega por dia (instâncias `sp_15`, `sp_40` e `sp_80`; 10 unidades reais do HC e as demais
sintéticas). Cada entrega tem peso, volume, prioridade (crítica, alta ou normal), pode exigir refrigeração e, se
for crítica, tem prazo. A frota é fixa e heterogênea:

| Tipo | Qtd | Capacidade | Autonomia | Velocidade | R$/km | Fixo/dia | Restrições |
|---|:-:|---|---|---|---|---|---|
| Moto | 2 | 15 kg / 40 L | 120 km | 35 km/h | 0,80 | 60 | não leva refrigerado nem volumoso |
| Carro | 2 | 150 kg / 400 L | 300 km | 28 km/h | 1,50 | 120 | — |
| Van | 1 | 800 kg / 3.000 L | 400 km | 24 km/h | 2,50 | 200 | — |

O código base da FIAP resolve um TSP (um veículo, cidades em pixels, distância euclidiana). O nosso problema é
um **VRP com frota heterogênea, capacidade, autonomia, prioridade, prazo, jornada e trânsito**. Toda decisão
abaixo partiu de uma pergunta: como chegar lá mudando o mínimo da estrutura do GA?

## 2. O que encontramos no código base e o que mudou

O código base (`reference/fiap_genetic_algorithm_tsp/`, guardado sem alterações) tem cinco problemas que
afetariam qualquer comparação (detalhes e trechos em `docs/do-tsp-ao-vrp.md`, seção 2):

1. **O crossover não mistura os pais:** `tsp.py` chama `order_crossover(parent1, parent1)`. Executando a função
   original, 10.000 de 10.000 filhos saíram idênticos ao pai; na prática o GA era "seleção + mutação".
2. **A mutação troca duas cidades adjacentes**, embora a docstring fale em inversão de segmento (há um `TODO`).
3. **Roleta com `1/distância`:** com distâncias parecidas, a pressão seletiva quase some.
4. **Sem seed nem critério de parada:** não dá para repetir um resultado, o que impede comparar configurações.
5. **Modelo mínimo:** um veículo, sem depósito, carga, prioridade ou tempo.

Resumo das mudanças (tabela completa, com o arquivo de cada uma, em `docs/do-tsp-ao-vrp.md`, seção 3):

| Componente | Código base | `medroute` |
|---|---|---|
| Representação | permutação de coordenadas (1 rota) | permutação de entregas (*giant tour*) + decoder que divide em rotas por veículo |
| Fitness | distância do ciclo | custo generalizado em R$ (operacional + prioridade + penalidades) |
| Seleção | roleta `1/fitness` | torneio (k = 3), independente da escala |
| Crossover | OX com o mesmo pai | OX e PMX, dois filhos por par, taxa 0,9 |
| Mutação | troca de vizinhos | swap, inversão de segmento, 2-opt no cromossomo |
| Elitismo | 1 | configurável (padrão 2) |
| Inicialização | aleatória | aleatória + semente do vizinho mais próximo (o `TODO` do original) |
| Busca local | — | 2-opt em km dentro de cada rota decodificada (GA híbrido) |
| Parada e reprodutibilidade | janela do pygame, `random` global | nº de gerações + paciência; `random.Random(seed)` por execução |
| Saída | desenho no pygame | `Solution` JSON (contrato com mapa, LLM e experimentos) |

## 3. Representação: *giant tour* + split

O cromossomo continua sendo uma permutação, como no código base, então OX, PMX e inversão funcionam sem
adaptação. A diferença é o significado: a permutação é a **ordem de visita de todas as entregas**, e o **decoder**
decide onde cortá-la e qual veículo faz cada trecho.

```
cromossomo:  [E07, E03, E12, E01, E09, E15, E04, ...]
                 └── moto-01 ──┘ └─── carro-01 ───┘ └─ van-01 ...
cada trecho: depósito → entregas na ordem do cromossomo → depósito
```

O decoder usado no fitness definitivo é o **split ótimo de Prins (2004)** (`ga/decoder.py::split_decode`):
programação dinâmica que, para cada prefixo do cromossomo e cada combinação de veículos já usados, guarda o menor
custo. Assim o GA busca só a **ordem**; a divisão em rotas e a escolha dos veículos são ótimas para aquela ordem.
O espaço de busca continua sendo n! e a frota heterogênea entra sem gene extra. Se não existir divisão viável, um
split guloso registra a violação em vez de descartar entregas.

Os baselines (vizinho mais próximo, NN+2-opt, Savings) usam o **mesmo split e o mesmo fitness**, então a
comparação mede só a qualidade da ordem encontrada.

## 4. Estratégias para as restrições

A decisão central (ADR 0004) foi expressar tudo em **reais**: somar quilômetros com prioridade não tem unidade, e
um custo em R$ é fácil de explicar e de comparar.

```
fitness = Σ rotas    [ custo_fixo_v + custo_km_v · km ]             # operacional
        + Σ entregas [ peso_prioridade · minutos até a chegada ]    # crítica 0,50 · alta 0,15 · normal 0,05 R$/min
        + Σ violações [ fixo + unitário · quantidade ]              # penalidades
```

Cada restrição tem uma estratégia, escolhida conforme ela possa ou não ser negociada na operação real:

| Restrição | Tipo | Como é tratada | Penalidade (`configs/fitness.yaml`) |
|---|---|---|---|
| Capacidade (kg e L) | hard | o split não forma trecho que estoure; penalidade só no fallback guloso | R$ 1.000 por rota + R$ 2.000 × fração excedida |
| Autonomia (km) | hard | idem | R$ 1.000 por rota + R$ 20/km acima |
| Compatibilidade (refrigerado/volumoso na moto) | hard | idem | R$ 1.000 por entrega incompatível |
| Prioridade | objetivo | custo por minuto até a chegada: a crítica "pesa" 10× a normal | 0,50 / 0,15 / 0,05 R$/min |
| Prazo das críticas | soft | entra no custo de cada trecho do split | R$ 10 por minuto de atraso |
| Jornada de 8 h | soft | idem | R$ 5 por minuto acima |
| Trânsito | modelo de tempo | as rotas saem às 07:00; cada trecho leva o fator da faixa em que começa (06–09 ×1,4; 09–17 ×1,0; 17–20 ×1,5) | — |
| Tempo de atendimento | modelo de tempo | 10 min por parada, somados à duração | — |

Duas camadas para as hard: o decoder evita a violação e a penalidade garante que, se ela acontecer, nunca
compense. As soft ficam no custo porque um atraso pequeno pode ser melhor que acionar mais um veículo, e essa
troca precisa ser visível para o GA. As funções de restrição vêm do módulo `constraints/` (Parte B, Beatriz) e são
as mesmas usadas pelos baselines e pela LLM (horários de chegada nas instruções vêm do mesmo `cronograma_rota`).

**Por que o trânsito importa:** com o fator ligado, chegar tarde no pico da manhã custa mais em prioridade. Foi
essa mudança que fez o GA híbrido passar a vencer o NN+2-opt com folga no `sp_40` (seção 6).

## 5. Operadores e o GA híbrido

Configuração das rodadas oficiais (`configs/experimentos/s2.yaml`): população 100, 300 gerações, crossover 0,9,
mutação 0,2 (inversão), elitismo 2, torneio 3.

Com o fitness definitivo e a frota completa, o **GA puro** perdia para o NN+2-opt avaliado com o mesmo split.
Duas mudanças, ambas sugeridas por lacunas do código base, resolveram:

1. **Semente NN:** um indivíduo da população inicial é a rota do vizinho mais próximo; o GA nunca começa pior que
   a heurística.
2. **2-opt dentro das rotas:** 30 % dos filhos passam por 2-opt em km em cada rota decodificada, e o resultado só
   substitui o filho se o fitness melhorar (busca local lamarckiana, GA memético).

O híbrido é o padrão do `medroute solve`; `--no-semente-nn --busca-local 0` volta ao GA puro.

## 6. Resultados

Dados reais com trânsito, 5 seeds (7, 17, 42, 73, 101), fitness em R$ (menor é melhor). V/E/D = vitórias,
empates e derrotas por seed contra o NN+2-opt. Fonte: `reports/comparativo-s2/summary.csv` e
`reports/comparativo-s1-atualizado-van/summary.csv`.

**`sp_40`, frota completa**

| Algoritmo | Fitness médio ± dp | Melhor | × NN+2-opt | Δ média | Km médios | Veículos | Tempo (s) |
|---|---|---|---|---|---|---|---|
| GA PMX (híbrido) | R$ 1.135,36 ± 72,57 | R$ 1.045,05 | 5/0/0 | −10,1 % | 208,2 | 4,4 | 106 |
| GA híbrido (OX) | R$ 1.145,65 ± 64,55 | R$ 1.058,53 | 5/0/0 | −9,3 % | 229,5 | 4,4 | 135 |
| NN+2-opt | R$ 1.263,23 | — | — | — | 235,2 | 5 | 23 |
| Savings | R$ 1.318,14 | — | — | +4,3 % | 219,8 | 5 | < 1 |
| GA puro | R$ 1.377,15 ± 119,34 | R$ 1.242,96 | 1/0/4 | +9,0 % | 333,7 | 4,6 | 64 |
| NN | R$ 1.432,09 | — | — | +13,4 % | 275,0 | 5 | < 1 |

**`sp_15`, frota completa**

| Algoritmo | Fitness médio ± dp | Melhor | × NN+2-opt |
|---|---|---|---|
| GA PMX (híbrido) | R$ 456,20 ± 3,18 | R$ 454,58 | 4/0/1 |
| GA híbrido (OX) | R$ 458,64 ± 5,12 | R$ 454,58 | 4/0/1 |
| NN+2-opt | R$ 461,72 | — | — |
| GA puro | R$ 472,48 ± 20,67 | R$ 455,41 | 2/0/3 |
| NN · Savings | R$ 474,44 · R$ 575,96 | — | — |

**`sp_15`, só a van (o TSP do código base, com o nosso fitness)**

| Algoritmo | Fitness médio ± dp | × NN+2-opt |
|---|---|---|
| GA híbrido | R$ 780,77 ± 1,52 | 4/0/1 |
| GA puro | R$ 782,34 ± 0,62 | 4/1/0 |
| NN+2-opt | R$ 782,90 | — |
| Savings · NN | R$ 3.268,15 · R$ 4.223,09 (violam o prazo das críticas) | — |

**`sp_80`** (CLI, híbrido, seed 7): R$ 2.714,96 (operacional R$ 1.114,50 + prioridade R$ 1.600,46), 363 km,
5 veículos, sem violação.

**Leitura.**

- No TSP (van única) o GA, puro ou híbrido, acha praticamente o mesmo que o NN+2-opt: com 15 entregas e um
  veículo, o 2-opt já chega perto do ótimo. A diferença aparece quando há divisão de rotas.
- Na frota completa o GA puro **perde** para o NN+2-opt, e o híbrido **vence**. A vantagem cresce com o tamanho:
  −0,7 % em `sp_15` e −9,3 % em `sp_40` (5 de 5 seeds). No `sp_40` o híbrido usa em média 4,4 veículos contra 5
  do NN+2-opt: a economia vem tanto de km quanto de custo fixo.
- Savings minimiza km, não custo generalizado: com uma van só ele faz menos km que o GA e mesmo assim atrasa
  críticas. É o argumento para o fitness em R$.
- O custo é tempo: o híbrido leva ~2 min no `sp_40` contra ~23 s do NN+2-opt. Para um planejamento diário, cabe.
- O desvio de ~R$ 65–73 no `sp_40` mostra que 300 gerações ainda não estabilizam a busca; o E1 (população e
  gerações) investiga isso.

## 7. Limitações

- Distância por haversine × 1,30 (tortuosidade), não por ruas reais (ADR 0003): os km são aproximados.
- Trânsito por faixa fixa de horário, sem dados reais de tráfego; todas as rotas saem às 07:00.
- Sem janelas de tempo para entregas não críticas (VRPTW ficou fora do escopo, P2).
- Custo fixo/dia e R$/km de van e motoboy não têm fonte (`configs/frota.yaml`, `fontes_pendentes`); a
  sensibilidade aos pesos é o experimento E5.
- Desvios-padrão descritivos (5 seeds, n−1), sem teste de significância.

## 8. Reprodução

```bash
medroute solve --inst sp_40 --seed 7                       # GA híbrido (padrão)
python -m medroute.experiments.runner --config configs/experimentos/s2.yaml --out reports/comparativo-s2
python scripts/compare_sp15.py --out reports/comparativo-s1-atualizado-van
```

Testes do GA: `tests/unit/ga/` (operadores preservam permutação e não alteram os pais; decoder; fitness) e
`tests/integration/`. Suíte completa em 22/10: 399 testes, `ruff check` ok.
