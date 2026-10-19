# Do TSP ao VRP: o que mudou em relação ao código base da FIAP

**Autor:** Conrado (Parte A) · **Requisito:** R10 ("partir do código base de TSP fornecido e modificá-lo")
**Código base:** `reference/fiap_genetic_algorithm_tsp/` (FIAP/genetic_algorithm_tsp, commit `d236a2a`), guardado sem
alterações. **Código novo:** `src/medroute/ga/` (Spec 02) e `src/medroute/ga/fitness.py` (Spec 03).

Este documento é a base da seção "antes × depois" do relatório. Cada linha da tabela da seção 3 aponta para o
arquivo onde a mudança está.

---

## 1. O código base em uma página

| Arquivo | O que faz |
|---|---|
| `genetic_algorithm.py` | População aleatória, fitness (distância euclidiana do ciclo), `order_crossover` (OX), `mutate` (troca de duas cidades adjacentes), `sort_population`. Tem um `__main__` próprio sem interface gráfica. |
| `tsp.py` | Laço principal com pygame: gera cidades aleatórias em pixels, avalia, ordena, desenha a melhor rota e a curva de fitness, monta a próxima geração. |
| `draw_functions.py` | Desenho das cidades, caminhos e do gráfico de convergência no pygame. |
| `benchmark_att48.py` | Coordenadas e rota ótima do benchmark att48 (uso opcional, comentado no `tsp.py`). |

O laço do `tsp.py` (linhas 341–358 do original):

```python
new_population = [population[0]]  # Keep the best individual: ELITISM
while len(new_population) < POPULATION_SIZE:
    probability = 1 / np.array(population_fitness)
    parent1, parent2 = random.choices(population, weights=probability, k=2)
    # child1 = order_crossover(parent1, parent2)
    child1 = order_crossover(parent1, parent1)
    child1 = mutate(child1, MUTATION_PROBABILITY)
    new_population.append(child1)
```

## 2. Problemas encontrados no código base

1. **O crossover não mistura os pais.** O `tsp.py` chama `order_crossover(parent1, parent1)`: o segmento vem do
   `parent1` e o preenchimento também, na mesma ordem, então o filho é **sempre uma cópia do pai**. Conferido
   executando a função original: 10.000 de 10.000 filhos idênticos ao pai. Na prática o GA do `tsp.py` é
   "seleção + mutação"; toda a variação vem do `mutate`. (O `__main__` do `genetic_algorithm.py` chama
   `order_crossover(parent1, parent2)` corretamente, mas é o `tsp.py` que o README manda executar.)
2. **A mutação é mais fraca do que a documentação diz.** A docstring de `mutate` fala em "inverter um segmento",
   mas o código troca duas cidades **adjacentes**; o próprio arquivo tem um `TODO` pedindo a inversão.
3. **Seleção por roleta com `1/distância`.** Com distâncias parecidas, os pesos ficam quase iguais e a pressão
   seletiva é baixa. A variante comentada ("10 melhores") vai para o outro extremo.
4. **Sem critério de parada nem reprodutibilidade.** `N_GENERATIONS = None` (roda até fechar a janela) e o
   `random` global não recebe seed: não dá para repetir um resultado, o que inviabiliza comparar configurações.
5. **Modelo do problema mínimo:** cidades em pixels, distância euclidiana, um veículo, sem depósito, sem carga,
   sem prioridade. O `TODO` da linha 300 sugere inicializar com vizinho mais próximo, o que não foi feito.

## 3. Antes × depois, componente por componente

| Componente | Código base (FIAP) | `medroute` | Onde |
|---|---|---|---|
| **Dados** | lista de `(x, y)` em pixels, gerada no script | `Instance` Pydantic (depósito, entregas com peso, volume, prioridade, refrigeração, deadline; frota) carregada de JSON e validada | `domain/models.py`, `data/loader.py` |
| **Distância** | euclidiana em pixels, recalculada a cada avaliação | haversine × fator de tortuosidade 1,30 em km, matriz pré-calculada; tempo pela velocidade de cada veículo | `data/distance.py`, ADR 0003 |
| **Representação** | permutação de coordenadas (1 rota) | permutação de IDs de entrega (*giant tour*) + **decoder** que corta em rotas por veículo | `ga/encoding.py`, `ga/decoder.py` |
| **Fitness** | distância total do ciclo | **custo generalizado em R$**: operacional (fixo + R$/km) + prioridade (R$/min até a chegada) + penalidades | `ga/fitness.py`, `configs/fitness.yaml`, ADR 0004 |
| **Seleção** | roleta `1/fitness` | torneio de tamanho *k* (padrão 3), independente da escala do fitness | `ga/operators.py::tournament_select` |
| **Crossover** | OX chamado com o mesmo pai (clona) | OX **e** PMX, dois filhos por par, com taxa de crossover | `order_crossover`, `pmx_crossover` |
| **Mutação** | troca de vizinhos | swap (dois pontos quaisquer), **inversão de segmento** (o `TODO` do original) e 2-opt sobre o cromossomo | `swap_mutation`, `inversion_mutation`, `two_opt_local` |
| **Elitismo** | 1 indivíduo | configurável (padrão 2) | `ga/engine.py::_next_generation` |
| **Inicialização** | aleatória | aleatória, com opção de semear o vizinho mais próximo (o `TODO` do original) | `nearest_neighbor_chromosome` |
| **Busca local** | — | 2-opt em km dentro de cada rota decodificada, aplicado a uma fração dos filhos (GA híbrido/memético) | `route_two_opt`, `GeneticAlgorithm._local_search` |
| **Parada** | nenhuma (janela do pygame) | nº máximo de gerações + paciência opcional (estagnação) | `GAConfig.generations`, `patience` |
| **Reprodutibilidade** | `random` global | `random.Random(seed)` por execução; mesma seed → mesma solução | `GeneticAlgorithm.run(seed)` |
| **Desempenho** | recalcula o fitness de todos | cache de fitness por cromossomo; matriz de distâncias pronta | `GeneticAlgorithm.score` |
| **Saída** | desenho no pygame | `Solution` JSON (rotas, custos, penalidades, histórico de fitness) — contrato único com mapa, LLM e experimentos | `domain/models.py::Solution` |
| **Visualização** | pygame + curva de fitness | mapa folium em HTML (cor por veículo, ícone por prioridade) | `viz/map.py` |
| **Parâmetros** | constantes no script | `GAConfig` validado, CLI `medroute solve` e YAML do runner | `ga/engine.py`, `app/cli.py`, `configs/experimentos/` |
| **Testes** | nenhum | testes de operadores (permutação válida, pais intactos), decoder, fitness e integração | `tests/unit/ga/`, `tests/integration/` |

## 4. Do TSP ao VRP: o *giant tour* e o split

O cromossomo continua sendo uma permutação, como no código base. Isso mantém os operadores de permutação (OX,
PMX, inversão) válidos sem adaptação. A diferença é que a permutação não é mais "a rota", e sim a **ordem de
visita de todas as entregas**; o **decoder** decide onde cortar essa sequência e qual veículo faz cada trecho.

```
cromossomo:  [E07, E03, E12, E01, E09, E15, E04, ...]
                 └── moto-01 ──┘ └─── carro-01 ───┘ └─ van-01 ...
rota de cada trecho: depósito → entregas na ordem do cromossomo → depósito
```

Dois decoders (Spec 02):

- **Split guloso (`decode`)** — percorre o *giant tour* e fecha a rota quando a próxima entrega não cabe em
  nenhum veículo livre; a rota fechada vai para o veículo viável mais barato. Simples e rápido, mas o corte
  depende só da ordem.
- **Split ótimo (`split_decode`, Prins 2004)** — programação dinâmica sobre os cortes possíveis e os grupos de
  veículos iguais: para cada prefixo do cromossomo e cada combinação de veículos usados, guarda o menor custo.
  O custo de cada trecho já inclui operacional, prioridade e as penalidades soft (deadline, jornada); trechos com
  violação hard (capacidade, autonomia, refrigeração, volumoso na moto) não entram. É o decoder usado com o
  fitness definitivo. Se nenhuma divisão viável existir, cai no guloso, que registra a violação em vez de
  descartar entregas.

Consequência para o GA: ele busca só a **ordem**; a divisão e a escolha de veículos são ótimas para cada ordem.
O espaço de busca é o mesmo do TSP (n! permutações) e a frota heterogênea entra sem gene extra.

## 5. Do "1/distância" ao custo em R$

```
fitness = Σ rotas [ custo_fixo_v + custo_km_v · km ]                  # operacional
        + Σ entregas [ peso_prioridade · minutos até a chegada ]      # crítica 0,50 · alta 0,15 · normal 0,05 R$/min
        + Σ violações [ fixo + unitário · quantidade ]                 # capacidade, autonomia, compatibilidade (hard)
                                                                       # deadline das críticas, jornada de 8 h (soft)
```

Somar tudo em reais resolve o problema de "somar km com prioridade" e torna o comparativo direto: GA e baselines
são avaliados pela mesma função (`make_fitness`) e pelo mesmo split. Os pesos ficam em `configs/fitness.yaml`
(o experimento E5 varia esses valores). As funções de restrição vêm do `constraints/` (Parte B).

## 6. Por que o GA virou híbrido

Com o fitness definitivo e a frota completa, o GA puro (só operadores genéticos) perdia para o vizinho mais
próximo + 2-opt avaliado com o mesmo split. Duas mudanças, ambas sugeridas por `TODO`s ou lacunas do código base,
resolveram:

1. **Semente NN:** um indivíduo da população inicial é a rota do vizinho mais próximo, então o GA nunca começa
   pior que a heurística.
2. **2-opt dentro das rotas:** 30 % dos filhos passam por 2-opt em km em cada rota decodificada; o resultado só
   substitui o filho se o fitness melhorar (busca local lamarckiana).

O híbrido é o padrão do `medroute solve`; `--no-semente-nn --busca-local 0` volta ao GA puro.

Resultados nos dados reais com fator de trânsito (19/10, 5 seeds, pop 100 × 300 gerações; ver
`PLANEJAMENTO.md` seção 8.1.6 e `reports/comparativo-s2/`):

| Cenário | NN+2-opt | GA puro | GA híbrido |
|---|---|---|---|
| `sp_15`, só a van (TSP) | R$ 782,90 | R$ 782,34 · vence 4/5, empata 1 | R$ 780,77 · vence 4/5 |
| `sp_15`, frota completa | R$ 461,72 | R$ 472,48 · vence 2/5 | R$ 458,64 · vence 4/5 (PMX: 4/5) |
| `sp_40`, frota completa | R$ 1.263,23 | R$ 1.377,15 · vence 1/5 | R$ 1.145,65 · vence 5/5 (melhor R$ 1.058,53) |

O GA puro perde para o NN+2-opt na frota completa; o híbrido vence, e a diferença cresce com o tamanho da
instância (−9% na média em `sp_40`).

## 7. Mapa dos arquivos

| Código base | `medroute` |
|---|---|
| `genetic_algorithm.generate_random_population` | `ga/encoding.py::create_population`, `nearest_neighbor_chromosome` |
| `genetic_algorithm.calculate_distance` | `data/distance.py::DistanceMatrix` |
| `genetic_algorithm.calculate_fitness` | `ga/decoder.py::split_decode` + `ga/fitness.py::Fitness` |
| `genetic_algorithm.order_crossover` | `ga/operators.py::order_crossover` (+ `pmx_crossover`) |
| `genetic_algorithm.mutate` | `ga/operators.py::swap_mutation`, `inversion_mutation`, `two_opt_local` |
| `genetic_algorithm.sort_population` + seleção do `tsp.py` | `ga/operators.py::tournament_select`, elitismo em `ga/engine.py` |
| laço do `tsp.py` | `ga/engine.py::GeneticAlgorithm.run` |
| `draw_functions.py` (pygame) | `viz/map.py` (folium) + `Solution.historico_fitness` |
| `benchmark_att48.py` | instâncias `data/instances/sp_15/40/80.json` (`medroute gen`) |
