# Conclusão

## 1. O que entregamos

| Pedido do enunciado | Como atendemos |
|---|---|
| GA para o TSP das entregas, a partir do código base | código base corrigido e estendido: *giant tour* + split ótimo, torneio, OX/PMX, inversão/swap, elitismo e GA híbrido com 2-opt |
| Fitness com distância, prioridade e restrições | custo generalizado em R$: operacional + R$/min até a chegada por prioridade + penalidades |
| Prioridade, capacidade, autonomia e vários veículos | frota de 5 veículos de 3 tipos; capacidade em kg e L, autonomia e compatibilidade como restrições duras |
| Outras restrições | prazo das críticas, jornada de 8 h, refrigerado/volumoso, tempo de atendimento e trânsito por faixa de horário |
| Mapa das rotas | mapa folium por veículo e prioridade, no CLI e no app |
| Instruções, relatórios e melhorias com LLM | instruções com horários, relatório diário/semanal com recomendações a partir de padrões calculados |
| Prompts eficientes e perguntas em linguagem natural | prompts versionados com fatos prontos; `medroute ask` com proteção contra *prompt injection*; rubrica automática |
| Projeto Python, documentação e testes | venv + `pyproject.toml`, specs, ADRs, diagramas Mermaid, 418 testes e CI |
| Comparativo, visualizações e análises | E1–E6 em três instâncias, cinco seeds, quatro heurísticas e dez figuras |

## 2. Principais resultados

- **O GA híbrido supera as heurísticas onde há divisão de rotas.** Em `sp_40` ele custa R$ 1.198,57 em média
  contra R$ 1.263,23 do NN + 2-opt (−5,1 %, vence nas 5 seeds) e R$ 1.318,14 do Savings.
- **O GA puro não basta.** Sem a semente do vizinho mais próximo e sem o 2-opt dentro das rotas, ele perde na
  média para o NN + 2-opt nas três instâncias. A hibridização é o que torna o GA competitivo.
- **A vantagem não é garantida.** Em `sp_80` o híbrido vence 4 de 5 seeds, mas a média empata com o NN + 2-opt
  (0,01 % acima) e 2 das 5 execuções passam da jornada. O melhor resultado (R$ 2.684,33) não tem penalidade.
- **Os parâmetros importam mais nas instâncias grandes.** Mutação 0,15 e crossover PMX reduzem a média e a
  dispersão em `sp_80`; aumentar a população reduz mais a dispersão que a média.
- **O preço da prioridade muda o plano.** Sem custo de prioridade o GA minimiza o custo operacional e as entregas
  prioritárias chegam mais tarde; com prioridade forte, a operação fica mais cara. O perfil equilibrado tem o menor custo comum.
- **Fatos prontos tornam a LLM confiável.** Com os números calculados em Python, o `gpt-4o-mini` passou nos 19
  casos da rubrica; o `gpt-oss-120b` (Groq) falhou só no relatório semanal, ao fazer contas e inventar metas.

## 3. Desafios e como resolvemos

| Desafio | Solução |
|---|---|
| O código base não cruzava os pais (crossover com o mesmo pai) e não tinha seed nem critério de parada | operadores reescritos, `random.Random(seed)` por execução, parada por gerações e paciência |
| Passar de uma rota (TSP) para vários veículos diferentes sem mudar o cromossomo | decoder com split ótimo de Prins: o GA busca a ordem; a divisão e os veículos saem por programação dinâmica |
| Comparar km, minutos, prioridade e violações | uma moeda só (R$), com pesos calibrados e em YAML |
| GA puro perdendo para uma heurística simples | semente NN na população e 2-opt dentro das rotas (GA memético) |
| LLM trocando horários, refazendo contas e inventando metas | o Python manda fatos prontos e confere a resposta; nova tentativa e texto padrão quando falha |
| Comparações justas entre algoritmos | mesmo split, frota, fitness e seeds para todos; validação independente de cada solução |
| Cinco pessoas trabalhando em paralelo | modelos congelados na primeira semana, specs com critérios de aceite e CI em todo PR |

## 4. Limitações

- **Distâncias aproximadas:** haversine × 1,30, não o traçado das ruas; trânsito por faixa fixa de horário, sem
  dados reais de tráfego.
- **Dados em parte simulados:** cargas, prioridades, prazos e domicílios são sintéticos (seed fixa); custos fixos
  por dia, R$/km da van e baú da moto são premissas sem fonte.
- **Escopo do modelo:** frota fixa, uma rota por veículo por dia, todas saindo às 07:00, sem janelas de tempo para
  as entregas não críticas.
- **Estatística descritiva:** cinco seeds por configuração, sem teste de significância; as melhorias de E2 e E3
  não foram testadas em conjunto.
- **Avaliação da LLM:** a rubrica confere forma e números, não a qualidade do raciocínio das recomendações.
- **Ponto de manutenção:** a validação dos experimentos encontrou dupla contagem de incompatibilidade no decoder
  quando uma entrega é refrigerada e volumosa ao mesmo tempo; ocorreu só em duas soluções inviáveis do aleatório
  e não altera nenhuma conclusão.

## 5. Próximos passos

- Distâncias e traçados reais com OSRM, já previstos na configuração.
- Janelas de tempo para todas as entregas (VRPTW) e mais de uma rota por veículo no dia.
- Combinar as melhores configurações de E2 e E3 e testar com mais seeds.
- Execução em nuvem com infraestrutura como código (opcional do enunciado, fora deste escopo pelo ADR 0002).

## 6. Reprodução

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.lock && pip install --no-deps -e .
pytest                                              # 418 testes
medroute demo                                       # fluxo ponta a ponta em sp_40 (LLM mock)
python -m medroute.experiments.study --render-only  # tabelas e figuras da S3
python scripts/build_relatorio.py                   # este PDF
```
