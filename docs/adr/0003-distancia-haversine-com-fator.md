# ADR 0003 — Distância haversine × fator de tortuosidade no core

- **Status:** Aceito
- **Data:** 2026-09-27
- **Decisores:** Luis Conrado (arquitetura); comunicado ao grupo por mensagem; aceite via aprovação do PR do plano

## Contexto
O GA precisa de uma matriz de distâncias entre depósito e ~40 entregas. Distância viária real exige um serviço
de roteamento (OSRM/OSMnx), que traz dependência de rede, latência e resultados não determinísticos entre
execuções — ruim para testes e para reproduzir experimentos.

## Decisão
A `DistanceMatrix` padrão usa **haversine × fator de tortuosidade** (1,3 para carro/van; 1,2 para moto), que
aproxima a distância urbana real de forma determinística e offline. O tempo usa a velocidade média do
veículo, com fator de trânsito por período em P1. OSRM fica em P2, atrás da mesma interface, apenas para
distâncias reais e para desenhar o traçado das ruas no mapa.

## Alternativas rejeitadas
- OSRM desde o início — dependência externa no caminho crítico de todos os módulos e dos testes.
- Distância euclidiana pura (como no código base de TSP) — subestima muito a distância urbana.

## Consequências
- Testes e experimentos são reproduzíveis sem internet.
- A interface `DistanceMatrix.dist()/time()` permite trocar a implementação sem tocar no GA.
- O relatório deve declarar o fator de tortuosidade como aproximação e citar a fonte.
