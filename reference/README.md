# reference/

Código base fornecido pela FIAP, guardado **sem modificações** para o "antes × depois" exigido pelo
enunciado (R10). Nada aqui é importado pelo `medroute` e a pasta fica fora do ruff.

| Pasta | Origem | Commit | Licença |
|-------|--------|--------|---------|
| `fiap_genetic_algorithm_tsp/` | <https://github.com/FIAP/genetic_algorithm_tsp> | `d236a2a` (25/06/2024) | CC0 1.0 |

Resumo do código base (ponto de partida do `docs/do-tsp-ao-vrp.md`):

- **Representação:** rota = lista de coordenadas `(x, y)` em pixels; 1 veículo, sem depósito fixo.
- **Fitness:** distância euclidiana total do ciclo (sem prioridade, capacidade ou autonomia).
- **Seleção:** roleta por `1/fitness` (`tsp.py`) ou sorteio entre os 10 melhores (`genetic_algorithm.py`).
- **Crossover:** OX (`order_crossover`). Em `tsp.py` é chamado como `order_crossover(parent1, parent1)`,
  ou seja, o crossover não mistura os pais.
- **Mutação:** troca de duas cidades adjacentes (o TODO no código pede inversão de segmento).
- **Elitismo:** 1 indivíduo; sem critério de parada (roda até fechar a janela do pygame).
- **Visualização:** pygame + matplotlib; benchmark `att48` opcional.
