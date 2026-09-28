# ADR 0006 — Spec-driven no nível "contratos entre módulos"

- **Status:** Aceito
- **Data:** 2026-09-27
- **Decisores:** Luis Conrado; comunicado ao grupo por mensagem; aceite via aprovação do PR do plano

## Contexto
Cinco pessoas trabalham em paralelo em módulos interdependentes (dados ? GA ? fitness ? LLM/visualização),
sem reuniões — só mensagens e GitHub. Na Fase 1 o pipeline era linear e a integração foi feita unificando
notebooks no final. Aqui, sem um formato combinado previamente, Rodrigo, Pedro e Alexandre ficam bloqueados
até o GA existir — ou cada um inventa o seu formato e a integração vira retrabalho.

## Decisão
Adotar spec-driven **apenas onde há interface entre duas pessoas**: specs formais (~1 página, com interface,
regras, critérios de aceite e testes) para domínio/dados, GA, fitness e LLM. Baselines, visualização e app
seguem com testes + README do módulo. `domain/models.py` é congelado em 30/09 e um `Solution` de exemplo fica
em `tests/fixtures/`, permitindo que todos comecem antes do GA existir.

## Alternativas rejeitadas
- Spec formal para todos os seis módulos — burocracia sem retorno em módulos que ninguém consome.
- Nenhuma spec, só "combinar no chat" — foi o que gerou a unificação tardia na Fase 1.

## Consequências
- Um dia da S0 para escrever e revisar as quatro specs.
- Mudanças em `models.py` exigem PR próprio e aviso no grupo.
- O relatório ganha a seção de decisões de projeto pronta (estes ADRs).
