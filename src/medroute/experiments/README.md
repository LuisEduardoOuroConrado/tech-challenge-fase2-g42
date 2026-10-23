# Experimentos e métricas

## Matriz E1–E6 — 23/10

`python -m medroute.experiments.study --workers 4` executa
`configs/experimentos/s3.yaml`. O runner da S2 descrito abaixo mantém sua API.

- `study.py`: valida o YAML, expande as variantes, deduplica receitas idênticas,
  executa processos independentes e grava um checkpoint por execução. `--workers 1`
  executa em série; a quantidade de workers não altera o RNG ou os resultados.
- `study_analysis.py`: revalida soluções, reavalia sob pesos comuns, audita
  compatibilidade e calcula estatísticas e pares por seed.
- `study_plots.py`: desenha convergência, dispersão e rotas em PNG/PDF.
- `study_report.py`: exporta tabelas, curvas compactadas e manifesto de artefatos.
- `--render-only`: lê os três JSONs em `reports/experimentos-s3/` e recria os
  derivados. Confere design, dados e fontes contra os hashes da rodada antes de
  exportar. Uma mudança nas fontes do otimizador exige uma nova rodada.

O YAML base descreve o GA híbrido; `ga` em cada variante sobrescreve somente os
campos indicados e passa pela validação de `GAConfig`. `priority_scale` multiplica
os preços por minuto de chegada, mantendo todas as penalidades. `baselines: true`
inclui NN, NN+2-opt (até 100 passagens), Savings e aleatório com os pesos oficiais.
`reference` escolhe a referência da comparação pareada dentro do experimento.

As 300 observações usam 240 execuções únicas; a mesma referência atende E1, E2,
E3, E5 e E6. Cada receita identifica algoritmo, parâmetros, seed, pesos, hashes
dos dados e fontes do otimizador e versão de Python. O executor tem hash e
proveniência separados. Checkpoints com hash inconsistente falham
explicitamente. Uma receita modificada não reutiliza a execução anterior.

Saídas em `reports/experimentos-s3/`:

| Arquivo | Conteúdo |
|---|---|
| `solutions.json` | Soluções únicas indexadas por hash da receita |
| `e6_solutions.json` | E6 como lista de `Solution`, compatível com `medroute report` |
| `design.json` | Vínculo experimento/configuração/instância/seed → execução |
| `metadata.json` | YAML resolvido, receitas, hashes, ambiente e concorrência |
| `metrics.csv` | 300 observações; fitness objetivo e comum, componentes, km, tempos e violações |
| `summary.csv` | Média, desvio amostral, mínimo e V/E/D por configuração/instância |
| `paired.csv` | Diferença e melhoria de fitness comum por seed contra `reference` |
| `convergence/E1.csv.gz` até `E6.csv.gz` | Fitness por passo/geração; `pd.read_csv` descompacta automaticamente |
| `resumo.md` | Tabelas e links para as figuras |
| `validacao.json` | Contagem de soluções revalidadas e hashes dos artefatos |
| `provenance/` | Executor original e auditoria da reutilização dos resultados |
| `evidencias/` | Testes, fluxo ponta a ponta e captura do Streamlit |

Por exemplo, `medroute report reports/experimentos-s3/e6_solutions.json --inst sp_80
--periodo semanal --provedor mock` exercita o relatório com os resultados reais da
rodada. A reanálise resolve os caminhos da máquina atual e confere os hashes de
conteúdo; preserva o Python e os caminhos da execução original como proveniência.

Na base `86276b9`, o decoder soma os atributos refrigerado e volumoso, enquanto
a função de restrições conta entregas incompatíveis. O validador confere o
fitness observado por atributo e exporta também `incompatibilidades_entregas`,
`incompatibilidades_duplicadas` e `fitness_sem_duplicacao`. A diferença apareceu
em duas soluções inviáveis do aleatório; não altera o ranking de E6. O otimizador
da base foi preservado, e os hashes das 229 soluções reaproveitadas podem ser
reconstruídos a partir da proveniência e do executor original arquivado.

As figuras PNG e PDF ficam em `reports/figuras/s3/`. E6 usa escala logarítmica
para comportar as penalidades do aleatório. Em E5 as barras usam pesos oficiais;
as curvas mostram porcentagem do fitness inicial de cada objetivo. Os mapas são
traçados esquemáticos das coordenadas, sem uma malha viária.
As instâncias são associadas às soluções pelo campo `nome` do JSON; o nome do
arquivo pode ser diferente, inclusive ao reanalisar os resultados.

O motor registra o melhor fitness de cada geração; sem elitismo ele pode subir.
O validador compara o mínimo do histórico com a solução global retornada e exige
monotonia somente quando o GA efetivo tem elitismo. As figuras usam o melhor
acumulado até cada geração. Com `patience`, as seeds podem parar em gerações
diferentes; para calcular média e desvio, o melhor acumulado de cada seed é
mantido até a última geração observada no seu grupo. Os JSONs e CSVs preservam
somente o histórico original dos pontos executados, sem preenchimento.

Cinco seeds permitem descrever a variabilidade observada; não há teste de
significância. Baselines determinísticos repetem o mesmo resultado nas seeds.
O tempo de cada otimizador exclui validação/renderização e é medido sob
concorrência, portanto não é um benchmark isolado. A retomada pode combinar
tempos observados em execuções diferentes, com receitas idênticas.

## Runner e métricas da entrega anterior

Entrega de 16/10 — Pedro, parte C. Runner para a matriz instância × seed ×
algoritmo, com quatro baselines e configurações nomeadas do GA.

## Reprodução

Na raiz do projeto, com o ambiente do README principal:

```bash
# S1 atualizada: uma van; GA puro/híbrido × quatro baselines, cinco seeds.
python scripts/compare_sp15.py
python scripts/compare_sp15.py --frota-completa

# S2: sp_15 e sp_40; GA puro, híbrido OX, híbrido PMX; cinco seeds.
python -m medroute.experiments.runner --config configs/experimentos/s2.yaml

# Sobrescrever seeds e destino.
python -m medroute.experiments.runner --config configs/experimentos/s2.yaml \
  --seeds 7 17 --out data/resultados/rodada_local
```

O runner executa NN, NN+2-opt, Savings, aleatório e cada configuração do GA para
cada instância/seed. Todos recebem a mesma matriz, frota, fitness definitivo e
split. Os GA têm motores/caches próprios por execução. NN é a referência da
mesma instância e seed. O 2-opt admite até 100 passagens (configurável).

`configs/experimentos/s2.yaml` exemplifica a configuração. Caminhos de entrada
e saída são relativos ao YAML, independentemente do diretório de execução.
`--out` é relativo ao diretório atual. Os campos obrigatórios são `name`,
`instances`, `fleet`, `fitness`, `ga_configs` e `out`. `seeds` tem padrão
`[7, 17, 42, 73, 101]`. `vehicles` restringe a frota efetiva; omitir usa toda ela.
Campos desconhecidos, listas vazias e seeds/instâncias/veículos repetidos são
rejeitados. Nomes de instância repetidos também são rejeitados para não misturar
os grupos estatísticos.

Cada chave de `ga_configs` recebe todos os campos de `GAConfig`; a solução
registra `algoritmo="ga_<nome>"`, por exemplo `ga_puro` e `ga_hibrido`. Isso
preserva o contrato de `Solution` e separa configurações no resumo e na LLM.
Para E5, outro YAML pode apontar para outros pesos em `fitness`.

## API para a CLI e outros consumidores

```python
from medroute.experiments.runner import load_experiment_config, run_experiment, write_results

config = load_experiment_config("configs/experimentos/s2.yaml")
result = run_experiment(config, progress=print)
write_results(result, config.out)
# result.solutions: list[Solution], compatível com mapa e LLM.
# result.metrics / result.summary: linhas para tabela ou CSV.
```

Arquivos exportados:

| Arquivo | Conteúdo |
|---|---|
| `solutions.json` | Todas as soluções, rotas, penalidades, seeds e históricos. |
| `metrics.csv` | Uma linha por instância/algoritmo/seed, melhorias contra NN. |
| `summary.csv` | Média, desvio amostral e mínimo por instância/algoritmo. |
| `convergence.csv` | Fitness por passo/geração e por execução, começando em zero. |
| `metadata.json` | Configuração efetiva, instâncias/frota/pesos, ambiente e hashes SHA-256 dos dados e fontes Python. |

No CSV de convergência, `passo` é geração apenas para GA. NN/Savings/aleatório
registram um ponto final; 2-opt registra inicial e final. O runner não gera
figuras nesta entrega; os históricos ficam disponíveis para E1–E6 em 23/10.
Os tempos variam com a máquina/carga; não constituem um estudo de desempenho.
O timestamp também varia, mas rotas, fitness e históricos se reproduzem com as
mesmas entradas, ambiente e seeds.

A rodada histórica de 09/10 foi preservada em `reports/comparativo-s1/`.
Usava fitness provisório; não deve ser comparada numericamente com as novas
rodadas. Resultados atuais e comandos exatos estão em
`reports/secoes/pedro-savings-runner-s2.md`.

## API de métricas

```python
from medroute.experiments import compare_solutions, extract_metrics, summarize_solutions

metrics = extract_metrics(solution)
rows = compare_solutions(solutions, reference=nn)
summary = summarize_solutions(solutions)
```

| Métrica | Significado |
|---|---|
| `fitness` | Custo generalizado informado pela solução, em R$. |
| `custo_operacional` | Soma do fixo e variável das rotas usadas, em R$. |
| `distancia_total_km` | Soma de ida, percurso e retorno ao depósito. |
| `duracao_total_min` | Esforço acumulado: soma das durações das rotas. |
| `duracao_max_min` | Maior duração; término se todos partirem juntos. |
| `veiculos_utilizados` | Número de rotas com entregas. |
| `entregas_atendidas` | Total de visitas nas rotas. |
| `rotas_com_violacao` | Rotas com pelo menos uma violação positiva. |
| `percentual_rotas_com_violacao` | Rotas violadas / rotas usadas × 100. |
| `penalidade_total` | Soma das penalidades monetárias em R$. |
| `tempo_exec_s` | Tempo informado pelo algoritmo. |

Violações em unidades diferentes não são somadas entre si; uma rota com vários
tipos conta uma vez. `compare_solutions` exige o mesmo nome de instância e
adiciona `100 × (referência − resultado) / referência` para fitness, custo e km.
Positivo indica redução; referência zero resulta em `None`.

`summarize_solutions` agrupa por instância/algoritmo. Para cada métrica numérica,
retorna `_media`, `_dp` (desvio amostral n−1, zero para uma execução) e `_min`,
além de execuções e percentual de execuções com violação. O mínimo é descritivo;
representa o melhor valor apenas em métricas a minimizar. Listas vazias geram
listas vazias. Fora do runner, o chamador precisa garantir as mesmas condições
e distinguir configurações no identificador do algoritmo.

## Validação

```bash
python -m pytest tests/unit/experiments tests/unit/baselines \
  tests/integration/test_experiments_sp40.py
```
