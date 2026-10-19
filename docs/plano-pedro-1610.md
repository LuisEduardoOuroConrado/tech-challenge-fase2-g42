# Entrega de Pedro — 16/10/2026

Base: `main` em `cf29b0c`; branch `feature/pedro-savings-runner-1610`, seguindo
`feature/pedro-baselines-0910`. Escopo: Clarke-Wright Savings, runner e atualização
do comparativo S1 com o fitness definitivo. E1–E6 completos continuam em 23/10.

## Plano

1. Verificar a base com pytest e ruff antes de alterar o código.
2. Alinhar a construção das soluções e o 2-opt ao decoder/split e às penalidades
   do GA quando recebem `make_fitness`, preservando a API anterior.
3. Implementar Clarke-Wright paralelo: savings em km, fusões nas extremidades,
   limites hard por veículo e desempates determinísticos. Usar as cadeias como
   giant tour para o decoder compartilhado atribuir a frota heterogênea finita.
4. Implementar runner e YAMLs: instâncias × configurações × seeds, com fitness
   comum, referência NN por seed, soluções, métricas, resumo, convergência e
   metadados com hashes dos dados e código.
5. Testar economias conhecidas, capacidade kg/L, autonomia, compatibilidade,
   preservação das entregas em frota insuficiente, P1, reprodução, configurações
   inválidas e exportação. Integração real em `sp_15` e `sp_40`.
6. Refazer o comparativo S1 (van e frota), exercitar três configurações em
   `sp_40`, registrar evidências e executar pytest completo, lint e smoke da CLI.

## Revisão do plano antes da implementação

- **Comparação justa:** passar a mesma instância, matriz, frota, pesos e split
  ao GA e baselines; incluir prioridade, deadline, jornada e atendimento.
- **Savings adaptado:** as economias escolhem a ordem; o split final pode mudar
  os limites das cadeias. Documentar a adaptação, sem apresentá-la como a
  atribuição clássica de veículos de Clarke-Wright para frota homogênea.
- **Frota insuficiente:** não descartar entregas; decoder registra violações.
- **Estatística:** identificar cada configuração como `ga_<nome>` para que o
  resumo não misture GA puro, híbrido e PMX.
- **Reprodução:** isolar RNG e cache de cada execução; salvar pesos, frota,
  instâncias efetivas, parâmetros, seeds e hashes. Tempos não são determinísticos.
- **Integração:** manter contratos de domínio e fornecer API para a futura CLI
  `compare`; não incluir os comandos da parte E neste escopo.

Plano revisado contra as Specs 02/03, cronograma e APIs da main. Base validada:
278 testes passando e ruff sem erros antes das mudanças.

## Revisão da implementação e validação

- Implementados Savings, integração dos baselines ao fitness definitivo, runner,
  YAMLs, exportação e documentação da API para a CLI futura.
- A revisão encontrou `scripts/criterio_s1.py` usando só uma passagem de 2-opt;
  ele agora chama o baseline público com o mesmo limite de 100 do comparativo.
  O critério pode registrar empates que a versão anterior contava como vitórias.
- Os 74 testes específicos passaram. A suíte completa passou com **315 testes**
  (37 a mais que a base), cobertura total **97%**, baselines **100%** e runner
  **97%**. Lint, formatação dos arquivos de código alterados, `git diff --check`
  e `medroute demo` passaram. Ambiente local: Python 3.12.14.
- A integração em `sp_40` verifica todas as entregas, fitness, penalidades,
  capacidade/autonomia/compatibilidade do Savings, mapa e relatório mock.
- Os dados da base `cf29b0c` foram preservados; os resultados identificam esses
  dados e precisam de nova rodada quando entrar a atualização de coordenadas.
- Evidências e análise final: `reports/secoes/pedro-savings-runner-s2.md`.
- Rodadas concluídas: 30 soluções no cenário de van e 70 na S2 (três
  configurações do GA × cinco seeds em `sp_15`/`sp_40`, mais quatro baselines).
  As 100 soluções e os hashes foram revalidados. Híbrido OX empata 5/5 com
  NN+2-opt na frota de `sp_15` e vence 2/5 em `sp_40`; os resultados completos
  incluem os casos piores e as penalidades dos baselines.
