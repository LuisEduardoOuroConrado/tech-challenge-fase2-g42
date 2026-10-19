# Savings e runner — entrega de Pedro em 16/10/2026

Branch: `feature/pedro-savings-runner-1610`, criada após pull da `main` em `cf29b0c`.

> **Atualização 19/10:** as pastas `reports/comparativo-s1-atualizado-van/` e `reports/comparativo-s2/`
> foram regeneradas com os mesmos comandos sobre os dados reais do PR #18 e o fator de trânsito do PR #21
> (`main` `646db7a`). Os resultados novos estão na seção 8.1.6 do `PLANEJAMENTO.md`. As tabelas abaixo são da
> rodada de 16/10 nas instâncias antigas; as evidências dela continuam no commit `7e2f971`.

## Entrega

Clarke-Wright Savings, runner de experimentos via YAML e atualização dos baselines
para o fitness definitivo da Spec 03. Todos recebem a mesma frota, matriz, pesos
e split do GA, incluindo prioridade, atendimento, deadline e jornada.

Savings usa economias em km para fundir extremidades de cadeias compatíveis com
kg/L, autonomia e carga. A adaptação concatena as cadeias e usa o split compartilhado
para atribuir a frota heterogênea finita; os cortes finais podem mudar. A busca por
economias em distância não otimiza diretamente prioridade/deadline.

O runner exporta `solutions.json`, `metrics.csv`, `summary.csv`, `convergence.csv`
e `metadata.json`. Cada configuração aparece como `ga_<nome>`, evitando misturar
execuções distintas no resumo. Os metadados incluem parâmetros efetivos, instâncias,
frota, pesos, ambiente e hashes SHA-256 dos arquivos de entrada e fontes Python.

## Reprodução e condições

```bash
python scripts/compare_sp15.py --out reports/comparativo-s1-atualizado-van
python -m medroute.experiments.runner --config configs/experimentos/s2.yaml \
  --out reports/comparativo-s2
```

Seeds: `7, 17, 42, 73, 101`. GA: população 100, 300 gerações, crossover 0,9,
mutação 0,2, elitismo 2, torneio 3 e mutação inversion. Puro usa OX sem semente NN
ou busca local. Híbrido usa OX, semente NN e busca local 0,3. PMX usa a mesma
configuração híbrida, trocando o crossover. 2-opt admite até 100 passagens.

O cenário TSP usa só a van em `sp_15`, com GA puro/híbrido. A S2 usa toda a frota
em `sp_15` e `sp_40`, com três configurações do GA. São 30 + 70 = 100 soluções.
Durações incluem atendimento e retorno. Trânsito permanece desligado
(`saida_min=None`), igual ao fitness atual do GA. Python local 3.12.14.

## Resultados

### sp_15 — van única

| Algoritmo | Fitness médio ± dp (R$) | Melhor (R$) | Km médios | Execuções com violação |
|---|---:|---:|---:|---:|
| ga_hibrido | 730.69 ± 1.99 | 729.80 | 104.77 | 0% |
| ga_puro | 730.61 ± 1.10 | 729.80 | 105.61 | 0% |
| nearest_neighbor | 3613.66 ± 0.00 | 3613.66 | 110.96 | 100% |
| nearest_neighbor_two_opt | 737.95 ± 0.00 | 737.95 | 109.48 | 0% |
| random | 7269.27 ± 2794.19 | 3825.30 | 224.08 | 100% |
| savings | 2205.86 ± 0.00 | 2205.86 | 103.39 | 100% |

Comparação pareada contra NN+2-opt (tolerância R$ 0,000001):

- `ga_hibrido`: 5 vitórias, 0 empates, 0 derrotas em 5 seeds.
- `ga_puro`: 5 vitórias, 0 empates, 0 derrotas em 5 seeds.

Evidências: [`comparativo-s1-atualizado-van`](../comparativo-s1-atualizado-van/summary.csv),
com [soluções](../comparativo-s1-atualizado-van/solutions.json),
[métricas](../comparativo-s1-atualizado-van/metrics.csv), [convergência](../comparativo-s1-atualizado-van/convergence.csv)
e [metadados](../comparativo-s1-atualizado-van/metadata.json).

### sp_15 — frota completa

| Algoritmo | Fitness médio ± dp (R$) | Melhor (R$) | Km médios | Execuções com violação |
|---|---:|---:|---:|---:|
| ga_hibrido | 431.02 ± 0.00 | 431.02 | 105.52 | 0% |
| ga_pmx | 428.27 ± 1.54 | 427.58 | 109.25 | 0% |
| ga_puro | 445.78 ± 21.05 | 427.58 | 127.85 | 0% |
| nearest_neighbor | 442.64 ± 0.00 | 442.64 | 111.76 | 0% |
| nearest_neighbor_two_opt | 431.02 ± 0.00 | 431.02 | 105.52 | 0% |
| random | 741.17 ± 66.93 | 675.63 | 225.15 | 0% |
| savings | 534.47 ± 0.00 | 534.47 | 105.73 | 0% |

Comparação pareada contra NN+2-opt (tolerância R$ 0,000001):

- `ga_hibrido`: 0 vitórias, 5 empates, 0 derrotas em 5 seeds.
- `ga_pmx`: 4 vitórias, 1 empate, 0 derrotas em 5 seeds.
- `ga_puro`: 1 vitória, 0 empates, 4 derrotas em 5 seeds.

Evidências: [`comparativo-s2`](../comparativo-s2/summary.csv),
com [soluções](../comparativo-s2/solutions.json),
[métricas](../comparativo-s2/metrics.csv), [convergência](../comparativo-s2/convergence.csv)
e [metadados](../comparativo-s2/metadata.json).

### sp_40 — frota completa

| Algoritmo | Fitness médio ± dp (R$) | Melhor (R$) | Km médios | Execuções com violação |
|---|---:|---:|---:|---:|
| ga_hibrido | 1076.84 ± 67.84 | 1003.96 | 233.99 | 0% |
| ga_pmx | 1045.00 ± 29.38 | 1016.70 | 256.78 | 0% |
| ga_puro | 1154.56 ± 55.67 | 1090.10 | 292.26 | 0% |
| nearest_neighbor | 1212.66 ± 0.00 | 1212.66 | 231.40 | 0% |
| nearest_neighbor_two_opt | 1035.36 ± 0.00 | 1035.36 | 257.82 | 0% |
| random | 3208.22 ± 1060.05 | 2315.78 | 627.80 | 100% |
| savings | 1454.95 ± 0.00 | 1454.95 | 191.36 | 100% |

Comparação pareada contra NN+2-opt (tolerância R$ 0,000001):

- `ga_hibrido`: 2 vitórias, 0 empates, 3 derrotas em 5 seeds.
- `ga_pmx`: 3 vitórias, 0 empates, 2 derrotas em 5 seeds.
- `ga_puro`: 0 vitórias, 0 empates, 5 derrotas em 5 seeds.

Evidências: [`comparativo-s2`](../comparativo-s2/summary.csv),
com [soluções](../comparativo-s2/solutions.json),
[métricas](../comparativo-s2/metrics.csv), [convergência](../comparativo-s2/convergence.csv)
e [metadados](../comparativo-s2/metadata.json).

## Interpretação e revisão

O comparativo de 09/10, mantido em `reports/comparativo-s1/`, usava fitness
provisório e não é numericamente comparável com esta rodada. Os resultados acima
usam a mesma função de avaliação e o mesmo split para GA e baselines.

Na revisão, `scripts/criterio_s1.py` aplicava apenas uma passagem de 2-opt.
O script agora chama o baseline público com até 100 passagens, assim como o runner.
Isso melhora a referência NN+2-opt e transforma algumas vitórias anteriores do
híbrido em empates na frota completa. Os números registrados na atualização da
main para o critério S1 usavam a referência com uma passagem; os critérios devem
ser lidos com esse parâmetro explícito.

Savings pode economizar quilômetros e ainda pagar penalidades por chegar tarde:
economias em distância não garantem menor custo generalizado. O cenário de van
única ilustra isso. Cada tabela informa violações, sem omitir as soluções piores.

Os baselines determinísticos repetem o resultado nas cinco seeds. O desvio zero
não representa cinco buscas independentes. Os desvios são amostrais (n−1),
descritivos; não foi aplicado teste de significância. Os tempos são informados
nos CSVs e dependem da máquina/carga. A ordem dos algoritmos é fixa.

Os dados são os da main `cf29b0c`; os hashes e snapshots identificam as coordenadas
usadas. Repetir as rodadas quando o PR de correção dos dados entrar.

## Validação

- Base antes da implementação: 278 testes e ruff verdes.
- Baselines/experimentos e integração nova: 74 testes passando.
- Projeto completo: **315 testes passando**, 37 a mais que a base.
- Cobertura completa: **97%**; baselines **100%**; runner **97%**.
- Lint, formatação dos arquivos de código alterados, `git diff --check` e `medroute demo`: aprovados.
- Integração real em `sp_40`: preservação das entregas, decomposição do fitness,
  penalidades definitivas, hard constraints do Savings, mapa folium e relatório mock.
- As 100 soluções salvas foram revalidadas contra as instâncias, fitness e penalidades;
  hashes das entradas e fontes conferidos após a execução.

```bash
python -m pytest --cov=medroute --cov-report=term-missing -q
python -m ruff check .
medroute demo
```

Os testes usam mock para a LLM; esta validação não chamou provedores reais.
E1–E6 completos, figuras e análise da entrega de 23/10 continuam no cronograma.
A API está pronta para a integração `medroute compare` da parte E.
