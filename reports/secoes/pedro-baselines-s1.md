# Comparativo inicial de roteamento — entrega de Pedro em 09/10

## Objetivo

Disponibilizar três abordagens de referência para comparar a qualidade das
soluções do algoritmo genético: Nearest Neighbor (NN), NN + 2-opt e aleatório.
Todas usam os mesmos contratos de domínio, decoder e fitness do GA, permitindo
consumo das soluções por mapas e demais componentes do projeto.

## Implementação

NN parte do depósito, escolhe a entrega não visitada mais próxima e desempata
pelo ID. NN + 2-opt usa essa ordem inicial e o operador existente de inversão
de segmentos; cada candidato passa pelo decoder e pela avaliação compartilhada.
A busca só aceita melhoria estrita e termina sem melhoria ou após 100 passagens.
O baseline aleatório gera uma única permutação com `random.Random(seed)` local.

Os algoritmos não omitem entregas e contabilizam retorno ao depósito. Em frota
insuficiente, o decoder preserva as entregas e registra as violações para a
penalização. As métricas separam esforço acumulado da frota (soma das durações)
e maior duração de rota. A estatística agrupa por instância e algoritmo e usa
desvio padrão amostral.

## Condições da execução

- Instância: `data/instances/sp_15.json`, 15 entregas.
- Frota: apenas `van-01`, com custo fixo de R$ 200 e R$ 2,50/km.
- Matriz: haversine com fator de tortuosidade de `configs/frota.yaml`.
- Seeds: 7, 17, 42, 73 e 101; os quatro algoritmos são avaliados em cada seed.
- GA: população 80, 200 gerações, OX, mutação inversion, crossover 0,9,
  mutação 0,2, elitismo 2 e torneio 3; sem parada antecipada.
- Fitness: implementação provisória de custo operacional + penalidades, sem
  custo de prioridade. Como todas as rotas desta rodada são viáveis e usam
  a mesma van, fitness = R$ 200 + R$ 2,50 × distância em km.
- Duração: somente viagem, conforme o decoder atual; sem tempo de serviço.
- Ambiente local: macOS arm64, Python 3.12.14, dependências de `requirements.lock`.
  A configuração de CI do repositório usa Python 3.11; os testes locais foram
  executados na versão informada acima.

Comando executado a partir da raiz do projeto:

```bash
python scripts/compare_sp15.py --out reports/comparativo-s1
```

## Resultados

| Algoritmo | Fitness médio ± dp (R$) | Melhor fitness (R$) | Distância média (km) | Tempo médio (s) |
|---|---:|---:|---:|---:|
| NN | 477,41 ± 0,00 | 477,41 | 110,96 | 0,000054 |
| NN + 2-opt | 456,39 ± 0,00 | 456,39 | 102,55 | 0,010393 |
| Aleatório | 760,21 ± 60,69 | 676,31 | 224,08 | 0,000044 |
| GA | 456,43 ± 1,90 | 454,49 | 102,57 | 0,115498 |

As 20 soluções cobrem as 15 entregas exatamente uma vez, utilizam uma van e
não registram violações. NN e NN + 2-opt são determinísticos; a mudança de seed
não altera suas rotas, logo o desvio de fitness é zero.

| Seed | Fitness do GA (R$) | GA vence NN? | GA vence NN + 2-opt? |
|---|---:|---|---|
| 7 | 454,49 | sim | sim |
| 17 | 458,30 | sim | não |
| 42 | 454,52 | sim | sim |
| 73 | 456,54 | sim | não |
| 101 | 458,30 | sim | não |

NN + 2-opt melhora o NN e fica muito próximo do GA nesta instância. O GA vence
NN nas cinco seeds, mas vence NN + 2-opt em apenas duas. Seu melhor resultado
supera NN + 2-opt, enquanto sua média é aproximadamente R$ 0,04 pior.
Portanto, o critério da S1 de que o GA vence os dois baselines foi verificado
para NN, mas não se confirmou de forma consistente para NN + 2-opt nesta rodada.

Os tempos são medições locais com relógio monotônico, incluindo a busca de cada
algoritmo e excluindo leitura dos dados e montagem da matriz. A ordem é fixa
(NN, NN + 2-opt, aleatório, GA); estes tempos são descritivos e não constituem
um estudo controlado de desempenho. Cinco seeds em uma instância não permitem
concluir superioridade geral nem significância estatística.

## Evidências e reprodução

- [Métricas por algoritmo e seed](../comparativo-s1/metrics.csv).
- [Resumo estatístico](../comparativo-s1/summary.csv).
- [Soluções completas](../comparativo-s1/solutions.json).
- [Parâmetros, ambiente e hashes SHA-256](../comparativo-s1/metadata.json).

Uma segunda execução confirmou igualdade das 20 soluções, inclusive rotas,
fitness e histórico, desconsiderando apenas `tempo_exec_s`. Os hashes dos dados
e das implementações foram conferidos após a execução.

## Validação e próximas etapas

Foram adicionados 38 testes de baselines, métricas e integração em `sp_15`.
`python -m pytest` passou com 168 testes; `python -m ruff check .` passou.
O código de GA, decoder, dados e modelos compartilhados foi preservado.

Quando o fitness definitivo entrar, repetir a comparação para incluir custo
de prioridade e as restrições atualizadas. Clarke-Wright Savings e o runner
de configurações ficam para 16/10; E1–E6 e a análise ampliada ficam para 23/10.
O comando `medroute compare` segue como integração da parte E.
