# Baselines de roteamento

Entrega de 09/10 — Pedro, parte C (baselines e experimentos).

Os três algoritmos recebem `Instance` e `DistanceMatrix` e devolvem `Solution`,
compatível com JSON, mapas e demais consumidores do projeto.

| Função pública | `Solution.algoritmo` | Estratégia |
|---|---|---|
| `solve_nearest_neighbor(inst, dm, *, seed=42, fitness_fn=None)` | `nearest_neighbor` | Parte do depósito e escolhe o vizinho não visitado mais próximo. Empates usam o ID da entrega. |
| `solve_nearest_neighbor_two_opt(inst, dm, *, seed=42, max_passes=100, fitness_fn=None)` | `nearest_neighbor_two_opt` | Começa no NN e aplica o operador 2-opt compartilhado até uma passagem sem melhoria ou o limite. |
| `solve_random(inst, dm, *, seed=42, fitness_fn=None)` | `random` | Uma permutação aleatória por execução, sem selecionar o melhor de vários sorteios. |

```python
from medroute.baselines import solve_nearest_neighbor, solve_nearest_neighbor_two_opt
from medroute.data import DistanceMatrix, load_fleet, load_instance

fleet = load_fleet("configs/frota.yaml")
inst = load_instance("data/instances/sp_15.json", fleet)
# Um veículo para a comparação TSP da S1.
inst = inst.model_copy(update={"fleet": [v for v in inst.fleet if v.id == "van-01"]})
dm = DistanceMatrix(inst, fleet)

nn = solve_nearest_neighbor(inst, dm, seed=7)
improved = solve_nearest_neighbor_two_opt(inst, dm, seed=7)
assert improved.fitness <= nn.fitness
print(improved.model_dump_json(indent=2))
```

## Regras compartilhadas com o GA

- A ordem das entregas é um giant tour: o depósito não é gene.
- `ga.decoder.decode` atribui veículos, separa rotas, contabiliza saída e retorno
  ao depósito e registra violações. Todas as entregas são preservadas, inclusive
  se a frota for insuficiente; uma solução pode ser inviável e será penalizada.
- O 2-opt reavalia o giant tour completo pelo decoder e pelo fitness. Em VRP,
  uma inversão pode mudar os pontos de separação e a atribuição de veículos.
- O fitness padrão é `ga.fitness.evaluate`, a mesma avaliação padrão do GA.
  `fitness_fn` permite fornecer a mesma função de avaliação aos dois; ela deve
  ser determinística e devolver um custo não negativo a minimizar. Assim como
  no GA atual, `Solution.penalidades` vem de `ga.fitness.penalties`.
- NN e NN + 2-opt são determinísticos e apenas registram a seed. O aleatório
  usa `random.Random(seed)` local, sem alterar o estado aleatório global.
- `tempo_exec_s` inclui construção da ordem, busca local, decode e avaliação;
  seu valor varia entre execuções. Não inclui carga dos arquivos nem montagem
  da matriz, que são comuns a todos os algoritmos na comparação.
- `historico_fitness` tem um valor final para NN/aleatório e dois valores
  (inicial e final) para NN + 2-opt. Não representa gerações do GA nem uma
  curva com cada passo da busca local.

## Limitações da S1

O fitness atual é provisório: custo operacional e penalidades, sem custo de
prioridade. A duração do decoder inclui apenas viagem, sem atendimento nas
paradas. Os baselines acompanham esses componentes e não duplicam restrições.
A comparação deve ser repetida quando o fitness definitivo estiver disponível.

Clarke-Wright Savings pertence à entrega de 16/10. O comando `medroute compare`
é uma integração posterior da parte E; nesta entrega há uma comparação
reproduzível em `scripts/compare_sp15.py`.

## Validação

```bash
python -m pytest tests/unit/baselines tests/integration/test_baselines_sp15.py
```

Os testes verificam a rota conhecida com retorno ao depósito, desempates,
melhoria 2-opt, reprodução por seed, uma entrega, split por capacidade,
frota insuficiente, contrato JSON e preservação da entrada.
