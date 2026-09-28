# ADR 0001 — Sem janelas de tempo completas (VRPTW)

- **Status:** Aceito
- **Data:** 2026-09-27
- **Decisores:** Luis Conrado (arquitetura); comunicado ao grupo por mensagem; aceite via aprovação do PR do plano

## Contexto
O enunciado pede restrições realistas (prioridade, capacidade, autonomia, múltiplos veículos) mas não pede
janelas de tempo. Modelar janelas `[início, fim]` para todas as entregas (VRPTW) exige decoder com espera,
operadores que preservem viabilidade temporal e uma bateria de testes muito maior.

## Decisão
Tempo entra de forma simplificada: tempo de viagem = distância / velocidade do veículo + 5 min de serviço;
**deadline apenas para entregas críticas** (penalidade soft) e **jornada máxima de 8 h por veículo** (soft).
VRPTW completo fica em P2 e só é considerado se P0 e P1 estiverem prontos e testados.

## Alternativas rejeitadas
- VRPTW completo para todas as entregas — dobra a complexidade do GA e dos testes sem exigência do enunciado.
- Ignorar tempo totalmente — perderia a noção de "crítico chega antes", que é o coração da prioridade.

## Consequências
- Prioridade e deadline usam `tempo_chegada_i`, calculado pelo decoder de forma barata.
- O relatório explica a simplificação como decisão consciente, não como omissão.
