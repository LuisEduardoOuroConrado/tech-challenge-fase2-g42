# Entrega de Pedro — 23/10/2026

Base: `main` atualizada por `git pull --ff-only origin main`, commit `86276b9`.
Branch: `feature/pedro-experimentos-2310`, no padrão das entregas de 09 e 16/10.
Escopo: experimentos E1–E6, tabelas, curvas, figuras e seção comparativa do relatório.

## Plano e revisão antes de implementar

1. Validar a base e conferir as entregas anteriores, cronograma e APIs atuais.
2. Versionar uma matriz YAML: três instâncias, cinco seeds (7/17/42/73/101),
   até 300 gerações; E1 população 50/100/200; E2 mutação 0,01/0,05/0,15;
   E3 OX/PMX; E4 swap/inversion/2-opt local; E5 custo/equilibrado/prioridade;
   E6 GA puro/híbrido e quatro baselines.
3. Executar trabalhos independentes com cache em disco, identidade por hashes,
   retomada e deduplicação da referência compartilhada entre experimentos.
4. Revalidar cada solução a partir dos dados: cobertura das entregas, rotas,
   métricas, violações, penalidades e fitness. Exportar dados e proveniência.
5. Gerar tabelas com média, desvio amostral, melhor, tempo, violações, comparação
   pareada por seed e curvas; figuras PNG/PDF para incorporar ao relatório.
6. Executar testes específicos e suíte completa, lint, CLI de ponta a ponta e
   Streamlit; revisar as figuras e a análise; commit, push e PR para `main`.

Decisões da revisão:

- Usar coordenadas reais, frota definitiva de 22/10 e trânsito da `main`.
- GA de referência: híbrido OX/inversion, população 100, 300 gerações, mutação
  0,05, crossover 0,9, elitismo 2, torneio 3, semente NN, busca local 0,3.
  E1/E2/E3 variam um fator, sem parada antecipada.
  Em E1 o número de avaliações nominais muda com a população: 15 mil, 30 mil
  e 60 mil; o controle é o número de gerações, não o orçamento de avaliações.
- E4 isola a operação aplicada com probabilidade 0,05: swap e inversion sem
  busca local adicional; 2-opt por rota usa `local_search_rate=0.05` e mutação
  aleatória zero. É o 2-opt em km já usado no híbrido, aceito só se reduzir o
  fitness; não é a busca exaustiva pelo fitness do operador `mutation=two_opt`.
- E5 muda apenas os preços de prioridade (0×, 1×, 3×); todas as penalidades
  permanecem. “Custo-puro” mantém a penalização de deadline/jornada e as
  restrições hard; o nome não significa um problema sem restrições.
  Exportar também fitness e prioridade sob os pesos oficiais comuns. Nunca
  ordenar perfis por fitness bruto de objetivos diferentes.
- E6 inclui GA puro e híbrido com o mesmo orçamento, split e fitness dos
  baselines. NN+2-opt usa até 100 passagens. Registrar também derrotas e empates.
- Cinco seeds são estatística descritiva; repetições de algoritmos
  determinísticos não são cinco evidências independentes. Tempo é observado
  sob concorrência e não serve como benchmark isolado de hardware.
- Reutilizar somente execuções com receita, entradas e fontes idênticas.
  Curvas têm geração zero na população inicial e incluem a solução final.
- Figuras científicas são artefatos Matplotlib estáticos, com versões PDF.
  A seção final precisa informar as limitações de haversine e dados simulados.

## Ajustes encontrados na validação

- A suíte encontrou diferenças de representação de `1`/`1.0` e de ordenação
  após salvar/reler o YAML. A escala agora tem padrão float; a reanálise
  compara as mesmas observações independentemente da ordem dos mapeamentos.
- A reanálise resolve caminhos locais e confere hashes de conteúdo/fontes,
  preservando o ambiente original nos metadados. Há teste de portabilidade
  simulando outra máquina e outra versão de Python, sem reotimizar as rotas.
- A inspeção do Streamlit revelou o mapa enquadrado como mapa-múndi quando o
  iframe era recriado numa aba oculta. `ResizeObserver` refaz o enquadramento
  na primeira dimensão visível. Fluxo reproduzido e correção verificada no
  navegador; testes existentes de mapa e Streamlit continuam passando.
- A rodada definitiva começou com quatro processos; 38 execuções concluídas
  foram reaproveitadas na retomada com oito. Tempos refletem essa concorrência
  e não sustentam uma comparação isolada de desempenho computacional.
- E6 também exporta uma lista de `Solution`, testada com `medroute report`,
  para consumir os resultados pelo fluxo existente da CLI.

## Evidências

- 240 execuções e 300 observações concluídas. As dez figuras PNG/PDF foram
  inspecionadas; curvas são compactadas por experimento para separar os commits.
- 412 testes passando, cobertura total 92%, `ruff check .` e `git diff --check`
  aprovados. Os testes incluem retomada, portabilidade, auditoria da
  compatibilidade, estatística pareada e exportação consumida pela CLI.
- CLI: demo completa em `sp_40` e solução S3 de `sp_80` (seed 42, fitness
  2.684,33, penalidades zero) em mapa → instruções → relatório semanal sobre
  30 soluções de E6 → pergunta. Streamlit validado por testes e pelo navegador.
- LLM mock nos fluxos desta entrega. Provedores reais não foram chamados.
- Auditoria: a base conta duas incompatibilidades para a mesma carga refrigerada
  e volumosa em moto. Duas soluções inviáveis do aleatório foram afetadas;
  ambas as contagens e o impacto de R$ 1.000 por solução estão nos dados.
  O otimizador foi preservado. A atualização do validador reutilizou 229
  soluções após conferir fontes do solver, entradas e parâmetros idênticos;
  executor original, hashes e mapeamento foram preservados em `provenance/`.
- Análise: `reports/secoes/pedro-experimentos-s3.md`. Manifesto e evidências:
  `reports/experimentos-s3/validacao.json` e `evidencias/`.
- Commits separados por desenho, execução, estatística, figuras, exportação,
  correção do mapa, dados de cada experimento, relatório e notebook.
