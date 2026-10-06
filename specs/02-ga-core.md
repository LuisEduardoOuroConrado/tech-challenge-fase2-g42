# Spec 02 — Núcleo do algoritmo genético

- **Responsável:** Luis Conrado
- **Status:** Aprovada em 05/10/2026 · implementada no PR #3
- **Revisor:** aprovação registrada pelo autor (sem revisor externo)
- **Escopo:** `src/medroute/ga/`

## Objetivo

O módulo recebe uma `Instance` e uma `DistanceMatrix`, busca uma permutação de
entregas de menor custo e devolve uma `Solution`. O mesmo núcleo deve atender à
etapa TSP, com um veículo, e à evolução para VRP, na qual o decoder separa a
permutação em rotas da frota disponível.

O fitness é sempre um **custo a minimizar**. Sua fórmula e suas penalidades são
definidas na Spec 03; o núcleo do GA apenas consome o valor retornado por ela.

## Representação

```python
Chromosome = list[str]  # IDs de todas as entregas, uma única vez
ScoreFunction = Callable[[Chromosome], float]
```

- O depósito não faz parte do cromossomo; cada rota começa e termina nele.
- Separadores e IDs de veículos não são genes.
- Crossover e mutação não podem alterar os cromossomos recebidos.
- Todo operador deve preservar exatamente o conjunto de IDs do pai.
- Cromossomos inválidos devem gerar `ValueError` antes da avaliação.

## Interface pública

```python
# ga/encoding.py
def create_individual(inst: Instance, rng: random.Random) -> Chromosome: ...
def create_population(
    inst: Instance,
    size: int,
    rng: random.Random,
) -> list[Chromosome]: ...
def validate_chromosome(chromosome: Chromosome, inst: Instance) -> None: ...

# ga/operators.py
def tournament_select(
    population: list[Chromosome],
    fitnesses: list[float],
    tournament_size: int,
    rng: random.Random,
) -> Chromosome: ...
def order_crossover(
    parent_a: Chromosome,
    parent_b: Chromosome,
    rng: random.Random,
) -> tuple[Chromosome, Chromosome]: ...
def pmx_crossover(
    parent_a: Chromosome,
    parent_b: Chromosome,
    rng: random.Random,
) -> tuple[Chromosome, Chromosome]: ...
def swap_mutation(chromosome: Chromosome, rng: random.Random) -> Chromosome: ...
def inversion_mutation(chromosome: Chromosome, rng: random.Random) -> Chromosome: ...
def two_opt_local(
    chromosome: Chromosome,
    score: ScoreFunction,
    max_passes: int = 1,
) -> Chromosome: ...

# ga/decoder.py
def decode(
    chromosome: Chromosome,
    inst: Instance,
    dm: DistanceMatrix,
) -> list[Route]: ...

# ga/engine.py
class GAConfig(BaseModel):
    population_size: int
    generations: int
    crossover_rate: float
    mutation_rate: float
    elitism: int
    tournament_size: int
    crossover: Literal["ox", "pmx"]
    mutation: Literal["swap", "inversion", "two_opt"]
    patience: int | None = None
    improvement_tolerance: float = 1e-9

class GeneticAlgorithm:
    def __init__(
        self,
        inst: Instance,
        dm: DistanceMatrix,
        config: GAConfig,
        fitness_fn: Callable[[list[Route]], float] = fitness.evaluate,
    ) -> None: ...

    def run(self, seed: int) -> Solution: ...
```

`fitness_fn` recebe as rotas decodificadas e devolve o custo a minimizar. O padrão
`ga/fitness.py` é provisório (custo operacional + penalidades da Spec 03, seção 4) e
será substituído pela implementação da Spec 03 sem mudar a assinatura do GA.

`two_opt_local` é uma busca local P1. O contrato já é definido para os
experimentos não precisarem mudar de formato quando ela entrar no GA.

## Regras de negócio

### Inicialização e seleção

1. A população inicial contém permutações válidas geradas pelo `rng` recebido.
2. O tamanho da população deve ser pelo menos 2.
3. Torneio amostra `tournament_size` indivíduos e retorna uma cópia daquele com
   menor fitness.
4. `tournament_size` deve estar entre 2 e o tamanho da população.

### Crossover e mutação

1. OX e PMX usam dois pontos de corte distintos e produzem dois filhos válidos.
2. Para cromossomos com menos de dois genes, os operadores retornam cópias sem
   alteração.
3. `swap` troca duas posições distintas.
4. `inversion` inverte o segmento inclusivo entre dois índices distintos.
5. `two_opt_local` aceita somente uma troca se ela não piorar o score e encerra
   ao atingir `max_passes` ou quando uma passagem não encontra melhora.
6. As taxas de crossover e mutação pertencem ao intervalo `[0, 1]`.

### Decoder TSP → VRP

1. O decoder preserva a ordem relativa do giant tour e não omite nem duplica
   entregas.
2. Na etapa TSP, com um veículo, é criada uma única rota.
3. Na etapa VRP P0, o decoder abre outra rota antes de exceder peso, volume ou
   autonomia sempre que houver um veículo viável disponível. Ao fechar uma rota,
   atribui o veículo livre mais barato que a comporta (custo fixo + custo por km);
   sem veículo viável, o de menor violação. Empates seguem a ordem da frota.
4. Somente veículos presentes em `Instance.fleet` podem aparecer nas rotas, no
   máximo uma rota por veículo.
5. Se a frota não comportar a instância, todas as entregas ainda devem aparecer
   em alguma rota. A violação deve ser registrada em `Route.violacoes` para que
   a Spec 03 aplique a penalidade; entrega inviável nunca é descartada.
6. Distância, duração, carga e custo da rota incluem saída e retorno ao depósito.
7. Para a mesma entrada, o decoder é determinístico.

### Evolução e parada

1. Cada geração avalia indivíduos decodificados usando a função da Spec 03.
2. Os `elitism` melhores indivíduos passam sem alteração para a próxima geração.
3. O melhor fitness de cada geração é anexado a `historico_fitness`; com
   elitismo maior que zero, o histórico não pode piorar.
4. A execução termina ao alcançar `generations` ou após `patience` gerações sem
   melhora superior a `improvement_tolerance`.
5. Toda aleatoriedade deriva de `random.Random(seed)`. Não usar o gerador global.
6. `Solution` contém a melhor solução observada, o seed recebido e o tempo total
   medido com relógio monotônico.

## Critérios de aceite

1. **Dado** um conjunto de IDs, **quando** qualquer operador genético é aplicado,
   **então** os filhos contêm os mesmos IDs exatamente uma vez.
2. **Dado** o mesmo problema, configuração e seed, **quando** o GA roda duas
   vezes, **então** rotas, fitness e histórico são iguais; apenas `tempo_exec_s`
   pode variar.
3. **Dada** uma instância com um veículo e capacidade suficiente, **quando** o
   cromossomo é decodificado, **então** há uma rota com todas as entregas na
   mesma ordem e retorno ao depósito contabilizado.
4. **Dada** uma entrega que excede a frota, **quando** ocorre o decode, **então**
   ela permanece na solução e a rota registra uma violação positiva.
5. **Dado** elitismo maior que zero, **quando** o GA executa várias gerações,
   **então** `historico_fitness[n + 1] <= historico_fitness[n]`.
6. **Dada** uma configuração com `patience`, **quando** não há melhora suficiente,
   **então** a execução para antes do limite de gerações.
7. **Dada** a execução concluída, **quando** a `Solution` é validada e serializada
   pelos modelos de domínio, **então** o JSON respeita a fixture
   `tests/fixtures/solution_sp15.json`.

## Testes obrigatórios

- Encoding: população válida, tamanho solicitado, reprodutibilidade e rejeição
  de cromossomo com ID ausente, extra ou duplicado.
- Operadores: OX, PMX, swap, inversion e 2-opt preservam permutação, não alteram
  os pais e tratam cromossomos de zero ou um gene; 2-opt nunca piora o score.
- Seleção: escolhe o menor fitness do torneio e valida seus limites.
- Decoder: rota única TSP, split por peso/volume, autonomia, frota insuficiente,
  métricas com retorno ao depósito e determinismo.
- Engine: seed reproduzível, elitismo, taxas zero e um, parada por gerações,
  parada por estagnação e preenchimento de `Solution`.
- Integração: executar `sp_15` e validar a solução serializada pelo Pydantic.

## Fora de escopo

- Fórmula do fitness e valores das penalidades (Spec 03).
- Geração, carga e matriz de distâncias das instâncias (Spec 01).
- Janelas de tempo completas, OSRM, zonas de circulação e otimização da
  quantidade de veículos como parte do cromossomo.
- Paralelização, execução em GPU e persistência da população.
