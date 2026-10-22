# Roteiro do vídeo — Tech Challenge Fase 2 · G42

- **Status:** rascunho 20/10/2026, com a rubrica da LLM (PR #27) e o app Streamlit (prazo do roteiro: 21/10; dono da parte E: Alexandre)
- **Duração-alvo:** 14 min (limite do enunciado: 15 min; 1 min de folga para a edição)
- **Gravação:** 27/10 (ter), cada um grava a sua parte (tela + voz). Edição: Alexandre, 28/10. Publicação
  (YouTube, não listado): 29/10.
- **Base:** enunciado (vídeo de demonstração), `PLANEJAMENTO.md` seções 7 e 8.2, `docs/arquitetura.md`,
  `docs/do-tsp-ao-vrp.md`

## O que o enunciado pede no vídeo

| Exigência | Onde entra |
|---|---|
| Demonstração do sistema em execução | blocos 3, 5 e 6 (CLI e Streamlit rodando ao vivo) |
| Explicação dos diferentes componentes da solução | blocos 1, 2 e 3 (arquitetura, GA, dados e restrições) |
| Apresentação dos resultados da otimização via GA | bloco 4 (comparativo com baselines e experimentos E1–E6) |
| Demonstração da integração com LLMs | bloco 5 (instruções, relatório e perguntas) |

## Visão geral

| # | Tempo | Quem | Bloco | Requisitos cobertos |
|---|---|---|---|---|
| 1 | 0:00–1:00 | Alexandre | Abertura: o problema e o que construímos | contexto |
| 2 | 1:00–4:00 | Conrado | Do TSP ao VRP: arquitetura e núcleo do GA | R1–R3, R7, R10, R17 |
| 3 | 4:00–6:30 | Beatriz | Dados reais e restrições, mapa | R4–R6, R8, R9 |
| 4 | 6:30–9:00 | Pedro | Resultados: GA × baselines e experimentos | R19 (comparativo) |
| 5 | 9:00–11:30 | Rodrigo | LLM: instruções, relatório e perguntas | R11–R15 |
| 6 | 11:30–14:00 | Alexandre | Demo ponta a ponta (Streamlit) e fechamento | R16, R18, demo |

Cada bloco abre com uma frase que liga ao anterior, para o corte da edição não ficar seco.

---

## Bloco 1 — Abertura (Alexandre, 1 min)

**Tela:** slide de título (grupo 42, nomes dos 5) → mapa de São Paulo com as unidades do HC.

**Fala-guia:**
- O hospital distribui medicamentos e insumos para unidades e atendimento domiciliar; parte das entregas é
  crítica e tem prazo.
- Construímos o `medroute`: um algoritmo genético que monta as rotas de uma frota heterogênea (motos, carros,
  van) e uma camada de LLM que transforma as rotas em instruções, relatórios e respostas.
- Princípio que atravessa o projeto: **o Python calcula, a LLM redige.**
- Roteiro do vídeo em uma frase: arquitetura → dados → resultados → LLM → demo.

## Bloco 2 — Do TSP ao VRP: arquitetura e GA (Conrado, 3 min)

**Tela:** `docs/arquitetura.md` (diagrama Mermaid) → `docs/do-tsp-ao-vrp.md` (antes × depois) → trechos de
`ga/decoder.py` e `ga/fitness.py`.

**Fala-guia:**
- Arquitetura em camadas: `domain` (modelos) → `data`/`constraints` → `ga` e `baselines` → `llm` → `app`
  (CLI e Streamlit). Todos trocam o mesmo `Solution`.
- Partimos do código base de TSP da FIAP (`reference/`) e mostramos o que mudou (R10).
- **Representação:** permutação das entregas (giant tour). O **decoder split** corta essa permutação em rotas
  ótimas por veículo, respeitando capacidade e autonomia como restrições duras.
- **Operadores:** seleção por torneio, crossover OX e PMX, mutação swap e inversão, elitismo; **GA híbrido**
  com 2-opt local.
- **Fitness em R$:** custo operacional (km e custo fixo por veículo) + custo de prioridade por minuto até a
  chegada (crítica 0,50 · alta 0,15 · normal 0,05 R$/min) + penalidades de deadline, jornada e compatibilidade.
  Uma moeda só torna os trade-offs comparáveis.
- Decisões registradas como ADRs em `docs/adr/`.

## Bloco 3 — Dados reais e restrições (Beatriz, 2,5 min)

**Tela:** terminal rodando `gen` e `solve` → mapa folium aberto no navegador.

```powershell
medroute gen
medroute solve --inst sp_40 --seed 7
```

**Fala-guia:**
- Instâncias `sp_15`, `sp_40` e `sp_80`: unidades reais do HC com coordenadas reais + domicílios sintéticos
  gerados com seed (reprodutível). Fontes da frota em `docs/fontes-frota.md`.
- Restrições: prioridade (crítico × regular), capacidade em kg e litros, autonomia em km, jornada de 8 h,
  deadline das críticas, compatibilidade carga × veículo (refrigerado, volumoso).
- **Fator de trânsito:** cada trecho leva o fator da faixa de horário em que sai (06–09 ×1,4; 09–17 ×1,0;
  17–20 ×1,5).
- No mapa: uma cor por veículo, ícone por prioridade, popup com horário de chegada.

## Bloco 4 — Resultados do GA (Pedro, 2,5 min)

**Tela:** `medroute compare` (tabela-resumo) → figuras dos E1–E6 em `reports/figuras/`.

```powershell
medroute compare
```

> O `compare` roda 5 seeds de todos os algoritmos e demora: gravar a saída antes ou mostrar a tabela já gerada
> em `reports/comparativo-s2/`.

**Fala-guia:**
- Baselines no mesmo split, frota e fitness: aleatório, Nearest Neighbor, NN + 2-opt e Clarke-Wright Savings.
- `sp_40`, frota completa, 5 seeds (com trânsito): GA híbrido **R$ 1.145,65** de média e GA PMX
  **R$ 1.135,36**, contra **R$ 1.263,23** do NN + 2-opt (cerca de 9% melhor) e R$ 1.318,14 do Savings. O
  híbrido vence o NN + 2-opt nas 5 seeds; o GA puro perde (1/0/4), que é o argumento para o híbrido.
- `sp_80`: R$ 2.714,96 com 5 veículos e sem violação.
- Experimentos E1–E6 (população, gerações, taxas, operadores): curvas de convergência e sensibilidade.
  **[PENDENTE: entrar com as figuras e os números finais do Pedro, prazo 23/10.]**

## Bloco 5 — Integração com LLM (Rodrigo, 2,5 min)

**Tela:** terminal com os três comandos → Markdown gerado aberto ao lado.

```powershell
medroute instruct data/resultados/sp_40_ga_vrp_s7.json --provedor openai
medroute report data/resultados/sp_40_ga_vrp_s7.json --periodo diario --provedor openai
medroute ask data/resultados/sp_40_ga_vrp_s7.json "A que horas são atendidas as entregas críticas e qual o prazo de cada uma?" --provedor openai
```

**Fala-guia:**
- Os fatos (ordem das paradas, horários, cargas, custos, violações) são montados em Python; a LLM só redige.
  Isso evita que ela invente números.
- **Instruções por motorista:** passo a passo da rota com o horário previsto de chegada a cada parada
  (cronograma do GA, saída às 07:00 com trânsito), com checagem de fidelidade de ordem e horários.
- **Relatório diário/semanal:** eficiência, economia e uma seção de recomendações (R13).
- **Perguntas em linguagem natural:** `medroute ask` sobre as rotas, com os mesmos horários das
  instruções. A pergunta da demo junta as críticas de todas as rotas com chegada e prazo, lista que o
  Python já entrega pronta (sem ela, o gpt-4o-mini trocava horários entre paradas vizinhas). Dado que
  não está no plano (ex.: nome do motorista) recebe "não disponível"; assunto sem relação, a recusa.
- Prompts versionados em `llm/prompts/`, cache de respostas e três provedores (mock, Groq, OpenAI).
- **Avaliação da qualidade** (mostrar `reports/avaliacao-llm/resumo.md`): rubrica determinística sobre a
  resposta crua de cada modelo, sem LLM-as-judge. Em `sp_40` (rodada oficial de 21/10), o gpt-4o-mini passa
  em todos os 19 casos (instruções com horários, relatório e 13 perguntas). O Groq passa em tudo menos no
  relatório semanal, que reprovou nas 4 rodadas: ele faz contas por conta própria ("110 min") e inventa
  limites ("90 %"). Por isso o relatório final e esta demo usam o gpt-4o-mini.

## Bloco 6 — Demo ponta a ponta e fechamento (Alexandre, 2,5 min)

**Tela:** Streamlit: escolher instância → otimizar → mapa → instruções → pergunta. Depois, GitHub com o CI verde.

```powershell
medroute app
```

> Para não esperar o GA na gravação: rodar antes `medroute solve --inst sp_40 --seed 7` e, no app, escolher
> **Usar solução salva**. Provedor `openai` na barra lateral, com o cache já aquecido no bloco 5.

**Fala-guia:**
- O mesmo fluxo dos blocos anteriores numa interface só: métricas (fitness, custo operacional, prioridade),
  mapa, tabela de rotas e curva de convergência; depois as abas de instruções, relatório e perguntas.
- Qualidade: projeto Python com venv e `pyproject.toml`, testes automatizados (385 hoje, incluindo o app e o
  fluxo da demo) e CI no GitHub Actions a cada PR.
- Fechamento: o que entregamos, limitações (distância haversine × fator, não ruas reais; frota fixa) e
  próximos passos.

---

## Checklist de gravação (27/10)

- [ ] Todos na `main` com a tag de release (mesmos números em todos os blocos).
- [ ] `.env` com `LLM_PROVIDER=openai` **só na máquina de quem grava o bloco 5** (crédito pré-pago). Rodar os
      comandos uma vez antes para aquecer o cache em `data/cache/llm/`: na gravação a resposta sai na hora e
      não cobra de novo.
- [ ] Mesma seed (7) e mesma instância (`sp_40`) em todos os blocos.
- [ ] Terminal com fonte grande (≥ 16 pt), tema escuro, janela em 1920×1080; fechar notificações.
- [ ] Nenhuma chave de API na tela (não abrir o `.env` durante a gravação).
- [ ] Arquivo entregue ao Alexandre como `bloco-N-nome.mp4`, com 1 s de silêncio no começo e no fim.
- [ ] Cada bloco dentro do tempo; se passar, cortar fala antes de cortar demo.
