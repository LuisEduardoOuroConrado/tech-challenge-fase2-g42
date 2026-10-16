# Baselines de roteamento

Entregas de 09/10 e 16/10 — Pedro, parte C.

Todos recebem `Instance` e `DistanceMatrix` e devolvem `Solution`, compatível
com JSON, mapas, instruções e relatórios do projeto.

| Função pública | `Solution.algoritmo` | Estratégia |
|---|---|---|
| `solve_nearest_neighbor(inst, dm, *, seed=42, fitness_fn=None)` | `nearest_neighbor` | Vizinho mais próximo; desempate pelo ID. |
| `solve_nearest_neighbor_two_opt(inst, dm, *, seed=42, max_passes=100, fitness_fn=None)` | `nearest_neighbor_two_opt` | NN seguido por inversões que reduzem o fitness do tour decodificado. |
| `solve_savings(inst, dm, *, seed=42, fitness_fn=None)` | `savings` | Clarke-Wright paralelo para ordenar cadeias, com split compartilhado. |
| `solve_random(inst, dm, *, seed=42, fitness_fn=None)` | `random` | Uma permutação por seed, sem selecionar o melhor de vários sorteios. |

```python
from medroute.baselines import solve_nearest_neighbor_two_opt, solve_savings
from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.ga import load_fitness_config, make_fitness

fleet = load_fleet("configs/frota.yaml")
inst = load_instance("data/instances/sp_40.json", fleet)
dm = DistanceMatrix(inst, fleet)
fitness_fn = make_fitness(inst, dm, fleet, load_fitness_config())
savings = solve_savings(inst, dm, seed=7, fitness_fn=fitness_fn)
nn_2opt = solve_nearest_neighbor_two_opt(inst, dm, seed=7, fitness_fn=fitness_fn)
print(savings.model_dump_json(indent=2))
```

## Fitness e restrições compartilhados

Com `make_fitness`, os baselines usam o mesmo `split_decode` do GA: custo
operacional + prioridade + penalidades de capacidade, autonomia, compatibilidade,
deadline e jornada. `FleetConfig` chega ao decoder, que inclui atendimento e
retorno na duração. `Solution.penalidades` usa os pesos definitivos. O trânsito
continua sem fator por período, conforme o fitness atual do GA (`saida_min=None`).

O 2-opt avalia cada inversão com esse mesmo split e fitness. Com frota finita,
uma inversão também pode alterar cortes e veículos. O limite de 100 passagens
vale para o runner e para `scripts/criterio_s1.py`; uma única passagem pode deixar
melhorias pendentes e produzir um baseline diferente.

Sem `fitness_fn`, permanece a API da S1: decoder guloso e fitness provisório,
sem prioridade, atendimento ou restrições P1. Funções customizadas recebem esse
decoder e as penalidades provisórias, como no GA com uma função customizada.
Para comparar com a CLI `solve`, passe sempre `make_fitness`.

## Clarke-Wright Savings

A economia de unir duas extremidades é `s(i,j) = d(0,i) + d(0,j) − d(i,j)`,
incluindo a saída e volta ao depósito. Começa com uma cadeia por entrega e
percorre economias positivas em ordem decrescente, desempate pelos IDs.
Só funde extremidades de cadeias distintas, invertendo-as quando necessário.
A cadeia unida precisa caber em pelo menos um veículo da instância (kg, L,
autonomia com retorno e compatibilidade). Deadline e jornada são soft e ficam
na avaliação monetária.

A adaptação para frota heterogênea finita concatena as cadeias em um giant tour
e delega os cortes e a atribuição ao decoder compartilhado. Assim, as fronteiras
das cadeias podem mudar no split final. Não é a atribuição clássica de veículos
homogêneos de Clarke-Wright, nem uma garantia de solução ótima. `savings_chains`
e `savings_order`, no módulo `savings`, permitem inspecionar esses dois estágios.

Nenhuma entrega é descartada se a frota for insuficiente: o decoder preserva
as visitas e registra violações. Cada veículo aparece em no máximo uma rota.

NN, 2-opt e Savings são determinísticos; a seed é registrada. O aleatório usa
`random.Random(seed)` local. `tempo_exec_s` inclui ordem, busca, decode e fitness;
exclui carga e montagem da matriz. `historico_fitness` tem valor final para
NN/Savings/aleatório e inicial/final para 2-opt; não são gerações do GA.

## Validação

```bash
python -m pytest tests/unit/baselines tests/integration/test_baselines_sp15.py \
  tests/integration/test_experiments_sp40.py
```

Há casos conhecidos de economia, limites em kg/L, autonomia com retorno,
refrigerado/volumoso, frota insuficiente, paradas/P1, mesmo split do GA,
reprodução por seed, JSON e integração com mapa e relatório mock.
