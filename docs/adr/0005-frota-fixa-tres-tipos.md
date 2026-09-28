# ADR 0005 — Frota fixa de três tipos de veículo

- **Status:** Aceito
- **Data:** 2026-09-27
- **Decisores:** Luis Conrado (arquitetura); comunicado ao grupo por mensagem; aceite via aprovação do PR do plano

## Contexto
O enunciado pede múltiplos veículos com capacidade e autonomia limitadas. É preciso decidir se o GA também
escolhe o tamanho/composição da frota ou se a frota é entrada do problema.

## Decisão
A frota é **entrada do problema**, definida em `configs/frota.yaml`: três tipos (moto, carro, van) com
quantidades, capacidade, autonomia, velocidade, custo/km, custo fixo e restrições de carga. O cromossomo é a
permutação das entregas (giant tour); o decoder distribui as entregas nos veículos disponíveis e o **custo
fixo** faz o GA usar menos veículos quando compensa. O GA não cria veículos nem altera a composição da frota.

## Alternativas rejeitadas
- Composição da frota como gene — problema de dimensionamento de frota (FSMVRP), outro nível de complexidade.
- Frota homogênea — perde a interação capacidade × custo que torna o problema interessante.

## Consequências
- Operadores clássicos de TSP (OX, PMX, swap, inversion, 2-opt) continuam válidos sem alteração.
- Experimentos podem variar a frota só editando o YAML.
- Valores iniciais são hipóteses; Beatriz levanta fontes (frete/km, autonomia, velocidade CET) até 07/10.
