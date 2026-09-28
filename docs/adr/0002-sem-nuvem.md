# ADR 0002 — Sem implantação em nuvem / IaC

- **Status:** Aceito
- **Data:** 2026-09-27
- **Decisores:** Luis Conrado (arquitetura); comunicado ao grupo por mensagem; aceite via aprovação do PR do plano

## Contexto
O enunciado marca a implementação em nuvem como **opcional**, valendo pontuação extra, e exigiria IaC,
arquitetura da solução e configuração de implantação como entregáveis adicionais.

## Decisão
O projeto roda localmente (CLI, notebook, Streamlit). Nenhum recurso de nuvem ou IaC é entregue.

## Alternativas rejeitadas
- Deploy do Streamlit + API em nuvem com Terraform — consumiria uma pessoa inteira das cinco, em um prazo
  curto, para um bônus incerto.
- Só o Streamlit Community Cloud (sem IaC) — não conta como "implementação em nuvem" pelos critérios do
  enunciado e adiciona dependência de chave de API pública.

## Consequências
- Todo o esforço vai para os requisitos obrigatórios e para o P1.
- Se sobrar tempo no fim, é P2 de baixíssima prioridade, atrás de OSRM e zonas de restrição.
