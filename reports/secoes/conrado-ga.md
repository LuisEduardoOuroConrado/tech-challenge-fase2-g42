# Algoritmo genético: do TSP ao VRP com frota heterogênea

**Autor:** Conrado (Parte A), com os dados e as restrições da Parte B (Beatriz) · **Requisitos:** R1–R10 e R19
(seções "GA a partir do código base" e "estratégias para as restrições") · **Base:** `docs/do-tsp-ao-vrp.md`,
`docs/arquitetura.md`, `docs/fontes-frota.md`, Specs 01, 02 e 03.

> **Revisado em 26/10.** Os resultados da seção 6 são os da rodada S3 de 23/10 (E6 em
> `reports/experimentos-s3/`, PR #37), a mesma fonte da seção de experimentos; a análise completa de E1–E6 está em
> `reports/secoes/pedro-experimentos-s3.md`. A frota foi fechada em 22/10 (`docs/fontes-frota.md` seção 2).

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
| Van | 1 | 650 kg / 3.100 L | 400 km | 24 km/h | 2,50 | 200 | — |

Referências: Honda CG 160 Cargo, Fiat Argo/Cronos e Fiat Fiorino (`docs/fontes-frota.md`). O R$/km é o custo total
do veículo por km rodado e o fixo/dia é a diária do condutor; a autonomia funciona como limite de km por jornada.

### Dados: instâncias, distância e tempo

As instâncias são geradas por `medroute gen` (`data/generator.py`, seed 42) e versionadas em `data/instances/`.
Mesma seed gera a mesma instância.

- **Depósito:** Farmácia Central do complexo HC-FMUSP.
- **Unidades reais:** 10 unidades da rede HC (InCor, ICESP, IPq, ICr, HU-USP, Cotoxó, IMREA Lapa, IOT, InRad e
  ICHC), com coordenadas por CEP (IBGE) conferidas no Google Maps em 14/10 (`docs/fontes-frota.md` seção 3). Sete
  ficam no próprio complexo, a menos de 0,4 km do depósito.
- **Domicílios sintéticos:** pontos sorteados num raio de 15 km do depósito, com carga menor que a das unidades.
- **Mix por quota exata:** 15 % críticas, 25 % altas, o resto normais; pelo menos 10 % refrigeradas. Cada crítica
  recebe um prazo de 120, 180, 240 ou 300 min a partir das 07:00. Cerca de um quarto das unidades tem item
  volumoso (> 60 L), que a moto não leva.

| Instância | Entregas (reais) | Crít. / alta / normal | Refrigeradas · volumosas | Carga total | Dist. média ao depósito |
|---|---|---|---|---|---|
| `sp_15` | 15 (4) | 2 / 4 / 9 | 2 · 2 | 102,7 kg · 303 L | 7,5 km |
| `sp_40` | 40 (10) | 6 / 10 / 24 | 4 · 6 | 220,0 kg · 822 L | 7,8 km |
| `sp_80` | 80 (10) | 12 / 20 / 48 | 8 · 4 | 269,5 kg · 996 L | 8,9 km |

Mesmo o `sp_80` cabe numa van só (270 kg de 650 kg). Dividir as rotas é uma questão de **tempo e prioridade**, não
de capacidade, e por isso o custo por minuto até a chegada pesa tanto no fitness.

`load_instance` valida cada instância antes do GA e junta todos os erros num único `DataError`: crítica sem
prazo, peso ou volume ≤ 0, entrega que nenhum veículo atende e carga total acima da frota.

**Distância e tempo** (`data/distance.py`, ADR 0003): a distância é haversine × 1,30 (fator de tortuosidade),
simétrica e calculada offline. O tempo de cada trecho é km ÷ velocidade do veículo × fator de trânsito da faixa
de horário em que o trecho começa. Todas as rotas saem às 07:00 e cada parada soma 10 min de atendimento.

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
troca precisa ser visível para o GA.

As medidas de violação ficam no módulo `constraints/` (Parte B, Beatriz). São funções puras e determinísticas que
devolvem 0 quando não há violação, e os pesos em R$ ficam fora delas, em `configs/fitness.yaml`:

| Função | Quantidade medida |
|---|---|
| `violacao_capacidade` | fração de excesso, somada em kg e em L: `max(0, kg/cap − 1) + max(0, L/cap − 1)` |
| `violacao_autonomia` | km acima da autonomia, com ida e volta ao depósito |
| `violacao_compatibilidade` | nº de entregas refrigeradas ou volumosas num veículo que não as aceita (não confere peso, para não cobrar a capacidade duas vezes) |
| `violacao_deadline` | soma dos minutos de atraso das críticas |
| `violacao_jornada` | minutos acima de 480, com viagem, paradas e volta |
| `cronograma_rota` · `duracao_rota` | minuto de chegada a cada entrega e duração total da rota, com o fator de trânsito |
| `custo_prioridade` | Σ peso da prioridade (R$/min) × minuto de chegada |

Essas funções são as mesmas para o GA, os baselines e a LLM. Os horários de chegada nas instruções aos motoristas
vêm do mesmo `cronograma_rota`.

**Por que o trânsito importa:** com o fator ligado, chegar tarde no pico da manhã custa mais em prioridade. Na
rodada de 19/10, foi essa mudança que fez o GA híbrido sair do empate e passar a vencer o NN+2-opt no `sp_40`
(`PLANEJAMENTO.md`, seções 8.1.5 e 8.1.6). A S3 confirma essa vitória (seção 6).

## 5. Operadores e o GA híbrido

Configuração de referência da rodada S3 (`configs/experimentos/s3.yaml`): população 100, 300 gerações, crossover
OX 0,9, mutação 0,05 (inversão), elitismo 2, torneio 3. O `medroute solve` usa mutação 0,2 por padrão, por isso
os números da demo não batem com os da seção 6.

Com o fitness definitivo e a frota completa, o **GA puro** perdia para o NN+2-opt avaliado com o mesmo split.
Duas mudanças, ambas sugeridas por lacunas do código base, resolveram:

1. **Semente NN:** um indivíduo da população inicial é a rota do vizinho mais próximo; o GA nunca começa pior que
   a heurística.
2. **2-opt dentro das rotas:** 30 % dos filhos passam por 2-opt em km em cada rota decodificada, e o resultado só
   substitui o filho se o fitness melhorar (busca local lamarckiana, GA memético).

O híbrido é o padrão do `medroute solve`; `--no-semente-nn --busca-local 0` volta ao GA puro.

## 6. Resultados

Rodada S3 (E6), dados reais com trânsito, 5 seeds (7, 17, 42, 73, 101), fitness em R$ (menor é melhor). V/E/D =
vitórias, empates e derrotas por seed contra o NN+2-opt. Fonte: `reports/experimentos-s3/summary.csv`.

**`sp_40`, frota completa**

| Algoritmo | Fitness médio ± dp | Melhor | × NN+2-opt | Δ média | Km médios | Veículos | Tempo (s) |
|---|---|---|---|---|---|---|---|
| GA híbrido | R$ 1.198,57 ± 58,01 | R$ 1.115,06 | 5/0/0 | −5,1 % | 227,9 | 4,6 | 29 |
| NN+2-opt | R$ 1.263,23 | — | — | — | 235,2 | 5 | 9 |
| Savings | R$ 1.318,14 | — | — | +4,3 % | 219,8 | 5 | < 1 |
| GA puro | R$ 1.325,65 ± 85,45 | R$ 1.223,34 | 2/0/3 | +4,9 % | 338,5 | 4,4 | 17 |
| NN | R$ 1.432,09 | — | — | +13,4 % | 275,0 | 5 | < 1 |

**`sp_15` e `sp_80`, frota completa**

| Algoritmo | `sp_15` | × NN+2-opt | `sp_80` | × NN+2-opt |
|---|---|---|---|---|
| GA híbrido | R$ 456,39 ± 2,54 | 5/0/0 · −1,2 % | R$ 2.884,40 ± 216,85 | 4/0/1 · +0,01 % |
| NN+2-opt | R$ 461,72 | — | R$ 2.884,01 | — |
| GA puro | R$ 474,74 ± 19,13 | 2/0/3 | R$ 7.709,24 ± 1.551,27 | 0/0/5 |
| NN · Savings | R$ 474,44 · R$ 575,96 | — | R$ 5.672,33 · R$ 4.413,51 | — |

**`sp_15`, só a van** (o TSP do código base com o nosso fitness; rodada de 19/10, mutação 0,2, em
`reports/comparativo-s1-atualizado-van/`)

| Algoritmo | Fitness médio ± dp | × NN+2-opt |
|---|---|---|
| GA híbrido | R$ 780,77 ± 1,52 | 4/0/1 |
| GA puro | R$ 782,34 ± 0,62 | 4/1/0 |
| NN+2-opt | R$ 782,90 | — |
| Savings · NN | R$ 3.268,15 · R$ 4.223,09 (violam o prazo das críticas) | — |

**Leitura.**

- No TSP (van única) o GA, puro ou híbrido, chega praticamente ao mesmo resultado do NN+2-opt: com 15 entregas e
  um veículo, o 2-opt já fica perto do ótimo. A diferença aparece quando há divisão de rotas.
- Na frota completa o GA puro **perde** na média para o NN+2-opt nas três instâncias, e o híbrido vence em
  `sp_15` (−1,2 %) e `sp_40` (−5,1 %, 5 de 5 seeds). No `sp_40` ele usa em média 4,6 veículos contra 5 do
  NN+2-opt: a economia vem de km e de custo fixo.
- Em `sp_80` o híbrido vence 4 de 5 seeds, mas uma execução pior deixa a média empatada (0,01 % acima). Em 2 das
  5 execuções ele passa da jornada de 8 h; nenhuma atrasa crítica nem viola restrição hard. O melhor resultado
  (seed 42, R$ 2.684,33) não tem penalidade. O híbrido não é ganho garantido em toda instância.
- Savings minimiza km, não custo generalizado: em `sp_40` faz menos km que o híbrido e custa mais. Com uma van só,
  atrasa críticas. É o argumento para o fitness em R$.
- O custo é tempo: o híbrido leva ~30 s no `sp_40` e ~110 s no `sp_80`. Para um planejamento diário, cabe.
- O desvio de ~R$ 58 no `sp_40` mostra que 300 gerações ainda não estabilizam a busca. E1 a E3 testam população,
  mutação e crossover: a mutação 0,15 e o PMX melhoram a média em `sp_80` (seção de experimentos).

## 7. Limitações

- Distância por haversine × 1,30 (tortuosidade), não por ruas reais (ADR 0003): os km são aproximados.
- Trânsito por faixa fixa de horário, sem dados reais de tráfego; todas as rotas saem às 07:00.
- Sem janelas de tempo para entregas não críticas (VRPTW ficou fora do escopo, P2).
- Cargas, prioridades, prazos e domicílios são simulados (seed fixa). As coordenadas das unidades reais são
  centroides de CEP ajustados à mão, com precisão de algumas centenas de metros. Sete das dez unidades ficam no
  complexo do depósito e custam quase nada de rota: a dificuldade vem dos domicílios.
- Custo fixo/dia dos três tipos, R$/km da van e capacidade do baú da moto são premissas sem fonte
  (`configs/frota.yaml`, `fontes_pendentes`); a sensibilidade aos pesos é o experimento E5.
- Desvios-padrão descritivos (5 seeds, n−1), sem teste de significância.

## 8. Reprodução

```bash
medroute solve --inst sp_40 --seed 7                       # GA híbrido (padrão)
medroute gen                                               # recria sp_15/40/80 (seed 42)
python -m medroute.experiments.study --render-only         # tabelas e figuras da S3 a partir das soluções salvas
python scripts/compare_sp15.py --out reports/comparativo-s1-atualizado-van
```

Testes: `tests/unit/ga/` (operadores preservam permutação e não alteram os pais; decoder; fitness),
`tests/unit/data/` e `tests/unit/constraints/` (gerador determinístico, validação, matriz de distâncias, cada
violação com caso zero, positivo e limite) e `tests/integration/`. Suíte completa em 26/10: 418 testes.
