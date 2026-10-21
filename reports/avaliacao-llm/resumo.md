# Avaliação da LLM — rubrica automática

- Instância: `sp_40` · soluções: `reports/comparativo-s2/solutions.json`
- Prompts: instrucoes_motorista v1, relatorio v1, qa v1
- Uma execução por caso (temperatura do `.env`). Tempo médio = resposta do modelo, sem as esperas por limite de taxa (429), que aparecem à parte.

Critérios conferidos na resposta crua da LLM, antes de nova tentativa ou texto padrão. Essenciais: Instruções: ordem_das_paradas, numeros_com_fonte, alertas_citados; Relatório: secoes, recomendacoes_3_a_5, numeros_com_fonte; Q&A: comportamento, numeros_com_fonte.

## Instruções

| Modelo | Casos | Aprovados | ordem_das_paradas | numeros_com_fonte | alertas_citados | Números sem fonte | Palavras | Tempo médio (s) | Espera por limite (s) | Novas tentativas |
|---|---|---|---|---|---|---|---|---|---|---|
| groq/openai/gpt-oss-120b | 4 | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 156 | 2,8 | 0,0 | 0 |
| openai/gpt-4o-mini | 4 | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 172 | 3,7 | 0,0 | 0 |

## Relatório

| Modelo | Casos | Aprovados | secoes | recomendacoes_3_a_5 | numeros_com_fonte | tamanho_200_a_350 | Números sem fonte | Palavras | Tempo médio (s) | Espera por limite (s) | Novas tentativas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| groq/openai/gpt-oss-120b | 2 | 50,0% | 100,0% | 100,0% | 50,0% | 0,0% | 1 | 407 | 3,3 | 56,0 | 0 |
| openai/gpt-4o-mini | 2 | 100,0% | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 310 | 4,0 | 0,0 | 0 |

## Q&A

| Modelo | Casos | Aprovados | comportamento | numeros_com_fonte | ate_150_palavras | Números sem fonte | Palavras | Tempo médio (s) | Espera por limite (s) | Novas tentativas |
|---|---|---|---|---|---|---|---|---|---|---|
| groq/openai/gpt-oss-120b | 10 | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 19 | 0,9 | 180,0 | 0 |
| openai/gpt-4o-mini | 10 | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 21 | 0,8 | 0,0 | 0 |

## Casos reprovados

- groq/openai/gpt-oss-120b · Relatório · semanal: numeros_com_fonte (sem fonte: 30)
