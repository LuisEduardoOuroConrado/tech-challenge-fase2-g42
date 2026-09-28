# ADR 0004 — Fitness como custo generalizado em R$

- **Status:** Aceito
- **Data:** 2026-09-27
- **Decisores:** Luis Conrado (arquitetura); comunicado ao grupo por mensagem; aceite via aprovação do PR do plano

## Contexto
O fitness precisa combinar distância, prioridade de entregas, uso de veículos e violações de restrições.
Somar quilômetros com "pontos de prioridade" gera pesos arbitrários difíceis de justificar; uma abordagem
multiobjetivo (Pareto / NSGA-II) resolve isso mas complica o GA, a comparação com baselines e a explicação.

## Decisão
O fitness é um **custo generalizado em reais, a minimizar**:
custo fixo por veículo usado + R$/km × distância + (peso da prioridade × tempo de chegada × R$/min) +
penalidades em R$ por violação (capacidade, autonomia, deadline, compatibilidade, jornada).
Pesos e penalidades vivem em `configs/fitness.yaml` e sua sensibilidade é um dos experimentos.

## Alternativas rejeitadas
- Soma ponderada de unidades heterogêneas (km + prioridade) — pesos sem interpretação.
- NSGA-II multiobjetivo — mais fiel, mas mais difícil de implementar, testar e comparar com NN/2-opt/Savings.

## Consequências
- GA e baselines são comparáveis numa única métrica com significado ("R$ por dia de operação").
- A frota heterogênea passa a fazer sentido: moto barata mas pequena × van cara mas grande.
- O relatório precisa justificar os valores de R$/km, custo fixo e R$/min de atraso (tarefa da Parte B).
