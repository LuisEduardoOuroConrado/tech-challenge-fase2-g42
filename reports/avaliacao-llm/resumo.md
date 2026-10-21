# Avaliação da LLM — rubrica automática

- Instância: `sp_40` · soluções: `reports/comparativo-s2/solutions.json`
- Prompts: instrucoes_motorista v2, relatorio v1, qa v1
- Uma execução por caso (temperatura do `.env`). Tempo médio = resposta do modelo, sem as esperas por limite de taxa (429), que aparecem à parte.

Critérios conferidos na resposta crua da LLM, antes de nova tentativa ou texto padrão. Essenciais: Instruções: ordem_das_paradas, horarios, numeros_com_fonte, alertas_citados; Relatório: secoes, recomendacoes_3_a_5, numeros_com_fonte; Q&A: comportamento, numeros_com_fonte.

## Instruções

| Modelo | Casos | Aprovados | ordem_das_paradas | horarios | numeros_com_fonte | alertas_citados | Números sem fonte | Palavras | Tempo médio (s) | Espera por limite (s) | Novas tentativas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| groq/openai/gpt-oss-120b | 4 | 100,0% | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 235 | 3,5 | 10,0 | 0 |
| openai/gpt-4o-mini | 4 | 100,0% | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 232 | 5,0 | 0,0 | 0 |

## Relatório

| Modelo | Casos | Aprovados | secoes | recomendacoes_3_a_5 | numeros_com_fonte | tamanho_200_a_350 | Números sem fonte | Palavras | Tempo médio (s) | Espera por limite (s) | Novas tentativas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| groq/openai/gpt-oss-120b | 2 | 0,0% | 100,0% | 100,0% | 0,0% | 50,0% | 2 | 354 | 3,1 | 60,0 | 0 |
| openai/gpt-4o-mini | 2 | 100,0% | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 320 | 4,4 | 0,0 | 0 |

## Q&A

| Modelo | Casos | Aprovados | comportamento | numeros_com_fonte | ate_150_palavras | Números sem fonte | Palavras | Tempo médio (s) | Espera por limite (s) | Novas tentativas |
|---|---|---|---|---|---|---|---|---|---|---|
| groq/openai/gpt-oss-120b | 10 | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 21 | 1,0 | 262,0 | 0 |
| openai/gpt-4o-mini | 10 | 100,0% | 100,0% | 100,0% | 100,0% | 0 | 22 | 1,0 | 0,0 | 0 |

## Casos reprovados

- groq/openai/gpt-oss-120b · Relatório · diario: numeros_com_fonte (sem fonte: 110)
- groq/openai/gpt-oss-120b · Relatório · semanal: numeros_com_fonte (sem fonte: 99)
