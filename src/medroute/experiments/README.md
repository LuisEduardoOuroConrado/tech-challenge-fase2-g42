# Métricas e comparação inicial

Entrega de 09/10 — Pedro, parte C (baselines e experimentos).

## API de métricas

```python
from medroute.experiments import compare_solutions, extract_metrics, summarize_solutions

metrics = extract_metrics(solution)
rows = compare_solutions([nn, improved, random_solution, ga], reference=nn)
summary = summarize_solutions(solutions)
```

`extract_metrics` devolve um dicionário com identificadores, seed e:

| Métrica | Significado |
|---|---|
| `fitness` | Custo generalizado informado pela solução; menor é melhor. |
| `custo_operacional` | Custo fixo e variável informado pela solução, em R$. |
| `distancia_total_km` | Soma das distâncias, incluindo retorno ao depósito. |
| `duracao_total_min` | Soma da duração das rotas usadas; esforço acumulado da frota. |
| `duracao_max_min` | Maior duração de rota; tempo até terminar se todos partirem juntos. |
| `veiculos_utilizados` | Número de rotas com entregas. |
| `entregas_atendidas` | Número de entregas nas rotas. |
| `rotas_com_violacao` | Rotas usadas com ao menos uma violação positiva. |
| `percentual_rotas_com_violacao` | Rotas violadas / rotas usadas × 100; zero sem rotas. |
| `penalidade_total` | Soma das penalidades monetárias de `Solution`, em R$. |
| `tempo_exec_s` | Tempo do algoritmo informado pela solução, em segundos. |

As quantidades de violações não são somadas entre tipos: excesso de capacidade
e quilômetros acima da autonomia têm unidades diferentes. Uma rota com várias
violações conta uma vez. A cobertura das entregas deve ser validada contra a
instância pelo chamador; `Solution` isolada não informa as entregas esperadas.

`compare_solutions` exige o mesmo `instance_nome` e adiciona o algoritmo de
referência e as melhorias percentuais de fitness, custo operacional e distância:

```text
melhoria (%) = 100 × (referência − resultado) / referência
```

Positivo indica redução, negativo indica piora, zero indica igualdade. Se a
referência vale zero, retorna `None` (indefinido), inclusive para 0 versus 0.
O chamador deve garantir a mesma instância, frota, matriz e função de avaliação;
o nome da instância sozinho não prova que as condições são iguais.

`summarize_solutions` agrupa por instância e algoritmo e devolve, para cada
métrica numérica, `_media`, `_dp` (desvio padrão amostral, n−1) e `_min`, além
do número de execuções e percentual de execuções com violação. Para uma única
execução, `_dp` é convencionado como zero. O mínimo é uma estatística descritiva;
somente para métricas a minimizar ele representa o melhor valor. Listas vazias
produzem listas vazias. Compare configurações distintas em chamadas separadas,
pois a configuração do GA não faz parte de `Solution`.

## Comparação inicial da S1

Na raiz do repositório, com o ambiente instalado conforme o README principal:

```bash
python scripts/compare_sp15.py
```

O script roda `sp_15` com uma van, GA com população 80 e 200 gerações,
OX/inversion, crossover 0,9, mutação 0,2, elitismo 2 e torneio 3; seeds
`7 17 42 73 101`. O 2-opt tem limite de 100 passagens. NN e NN + 2-opt
produzem a mesma rota nas cinco seeds; o desvio zero desses algoritmos é
consequência de serem determinísticos.

```bash
python scripts/compare_sp15.py --seeds 7 17 42 73 101 --veiculo van-01 \
  --out data/resultados/comparativo_s1
```

Arquivos de saída:

- `solutions.json`: as soluções completas, incluindo rotas e histórico do GA.
- `metrics.csv`: uma linha por algoritmo e seed, com comparação contra NN.
- `summary.csv`: médias, desvios amostrais e mínimos por algoritmo.
- `metadata.json`: parâmetros, ambiente e hashes SHA-256 dos arquivos de entrada
  e implementação, para identificar as condições da comparação.

As saídas padrão ficam em uma pasta ignorada pelo Git. O registro da entrega em
`reports/comparativo-s1/` e a análise em `reports/secoes/pedro-baselines-s1.md`
documentam a execução inicial. Os tempos dependem da máquina e da carga do
sistema; a ordem de execução dos algoritmos é fixa, sem estudo de desempenho.
Esta rodada não substitui os experimentos E1–E6 nem o runner previsto para 16/10.

## Validação

```bash
python -m pytest tests/unit/experiments tests/integration/test_baselines_sp15.py
```
