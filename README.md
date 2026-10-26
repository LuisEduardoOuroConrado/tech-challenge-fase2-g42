# medroute

Otimização de rotas para distribuição de medicamentos e insumos com algoritmo genético, frota
heterogênea e apoio de LLM. Tech Challenge Fase 2 da FIAP Pós Tech (IA para Devs), Projeto 2, Grupo 42.

| Entregável | Onde |
|---|---|
| Relatório técnico (PDF) | [`reports/relatorio/relatorio-tecnico-g42.pdf`](reports/relatorio/relatorio-tecnico-g42.pdf) |
| Vídeo de demonstração | *a publicar* |
| Código-fonte | [`src/medroute/`](src/medroute/) |
| Demonstração | `medroute demo`, `medroute app` e [`notebooks/`](notebooks/) |

## O que o sistema faz

- **Dados:** instâncias `sp_15`, `sp_40` e `sp_80` com 10 unidades reais do HC-FMUSP e domicílios
  sintéticos (seed fixa); frota de 2 motos, 2 carros e 1 van com números conferidos em fontes públicas.
- **Otimização:** GA híbrido para o VRP com frota heterogênea, a partir do código base de TSP da FIAP.
  Capacidade, autonomia, prioridade, prazo das críticas, jornada de 8 h e trânsito por faixa de
  horário entram num único custo em R$.
- **Comparação:** aleatório, vizinho mais próximo, NN + 2-opt e Clarke-Wright Savings com o mesmo
  split e a mesma função de custo; experimentos E1–E6 com 240 execuções.
- **LLM:** instruções por motorista com horários, relatórios diário e semanal com recomendações e
  perguntas em linguagem natural. O Python calcula os fatos; a LLM só redige, e o código confere.
- **Visualização:** mapa folium por veículo e prioridade, app Streamlit com o fluxo completo e
  notebooks com saídas salvas.

## Resultados (rodada S3, 23/10)

Fitness médio em R$ (custo generalizado, menor é melhor), 5 seeds, frota completa com trânsito.
V/E/D = vitórias, empates e derrotas por seed contra o NN + 2-opt.

| Algoritmo | `sp_15` | `sp_40` | `sp_80` |
|---|---|---|---|
| GA híbrido | **456,39** | **1.198,57** | 2.884,40 |
| NN + 2-opt | 461,72 | 1.263,23 | **2.884,01** |
| GA puro | 474,74 | 1.325,65 | 7.709,24 |
| Savings | 575,96 | 1.318,14 | 4.413,51 |
| Híbrido × NN + 2-opt | 5/0/0 · −1,2 % | 5/0/0 · −5,1 % | 4/0/1 · +0,01 % |

Em `sp_80` o híbrido vence 4 de 5 seeds, mas a média empata. Tabelas completas, figuras e análise:
[`reports/experimentos-s3/resumo.md`](reports/experimentos-s3/resumo.md) e
[`reports/secoes/pedro-experimentos-s3.md`](reports/secoes/pedro-experimentos-s3.md).

## Ambiente local

Requer Python 3.11.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

No Linux ou macOS, ative o ambiente com `source .venv/bin/activate`. Para a LLM real, copie
`.env.example` para `.env` e preencha `GROQ_API_KEY` ou `OPENAI_API_KEY`; sem chave, o provedor
`mock` roda tudo sem rede.

## Verificação

```powershell
python -m ruff check .
python -m pytest              # 418 testes
medroute demo --rapido
```

## Demonstração

```bash
medroute demo                      # sp_40, GA híbrido completo (~2 min), LLM mock
medroute demo --provedor openai    # mesma demo com as respostas reais da LLM (chave no .env)
medroute demo --rapido             # GA reduzido, roda em segundos
medroute app                       # app Streamlit em http://localhost:8501
```

A demo roda o fluxo ponta a ponta: GA híbrido + mapa → instruções por motorista → relatório semanal →
pergunta em linguagem natural, e salva tudo em `data/resultados/demo/`. Com `mock` a LLM devolve os
fatos que recebeu em vez de redigir o texto.

O app Streamlit abre o mesmo fluxo numa tela: instância → otimizar com o GA (ou carregar um JSON
salvo) → métricas, mapa, rotas e convergência → instruções, relatório e perguntas. O provedor da LLM
é escolhido na barra lateral; respostas reais ficam em cache em `data/cache/llm/`.

Notebooks com as saídas salvas (`python -m pip install -e ".[notebook]"` para executá-los):

- [`notebooks/01_demo_completa.ipynb`](notebooks/01_demo_completa.ipynb): dados, GA × baselines,
  rotas, convergência, mapa e LLM;
- [`notebooks/02_experimentos.ipynb`](notebooks/02_experimentos.ipynb): tabelas e figuras de E1–E6.

## CLI

```bash
medroute gen                                   # instâncias sp_15, sp_40, sp_80
medroute solve --inst sp_40 --seed 7           # GA híbrido -> data/resultados/*.json + mapa
medroute map data/resultados/sp_40_ga_vrp_s7.json
medroute instruct data/resultados/sp_40_ga_vrp_s7.json          # instruções por motorista (LLM)
medroute compare --config configs/experimentos/s2.yaml --seed 7 # GA × baselines (runner)
medroute report data/resultados/comparativo_s2/solutions.json --inst sp_40 --periodo semanal
medroute ask data/resultados/sp_40_ga_vrp_s7.json "Qual veículo chega mais tarde e por quê?"
```

`instruct`, `report` e `ask` usam o `LLM_PROVIDER` do `.env`; `--provedor mock|groq|openai`
sobrescreve só naquele comando. O `report` aceita uma ou mais `Solution` ou o `solutions.json` do
`compare`; com várias instâncias, `--inst` escolhe uma.

## Experimentos E1–E6

```bash
python -m medroute.experiments.study --workers 4
# Recria tabelas e figuras das soluções salvas, sem otimizar novamente:
python -m medroute.experiments.study --render-only
```

A matriz em [`configs/experimentos/s3.yaml`](configs/experimentos/s3.yaml) cobre `sp_15`, `sp_40` e
`sp_80`, cinco seeds e 300 gerações, com a frota definitiva e trânsito: 300 observações e 240
execuções únicas. O cache em `data/resultados/experimentos_s3_cache/` permite retomar uma execução
interrompida; receitas, dados e fontes têm hashes. Tempos foram medidos sob concorrência; cinco seeds
fornecem estatística descritiva, sem teste de significância. Detalhes em
[`src/medroute/experiments/README.md`](src/medroute/experiments/README.md) e no
[plano revisado](docs/plano-pedro-2310.md).

## Relatório

```bash
python scripts/build_relatorio.py                        # gera o PDF a partir dos capítulos
python scripts/build_relatorio.py --video <link>         # com o link do vídeo na capa
```

Os capítulos ficam em [`reports/relatorio/`](reports/relatorio/) (introdução, visualização e
conclusão) e [`reports/secoes/`](reports/secoes/) (GA, LLM e experimentos). O script usa o Chrome
headless para imprimir o PDF e desenhar os diagramas Mermaid.

## Estrutura

```
src/medroute/
  domain/        modelos Pydantic (entrega, veículo, instância, rota, solução)
  data/          gerador de instâncias, validação, frota, matriz de distâncias e tempos
  constraints/   cronograma, custo de prioridade e violações
  ga/            representação, operadores, decoder (split ótimo), fitness em R$, motor do GA
  baselines/     NN, NN + 2-opt, Savings e aleatório
  experiments/   runner, estudo E1–E6, estatísticas e figuras
  llm/           cliente, prompts versionados, instruções, relatórios, Q&A e avaliação
  viz/ app/      mapa folium, CLI e app Streamlit
configs/         frota, pesos do fitness e matrizes de experimentos
data/instances/  sp_15, sp_40 e sp_80
reports/         relatório, seções, experimentos, avaliação da LLM e figuras
docs/            arquitetura, do TSP ao VRP, fontes da frota, prompts, ADRs e roteiro do vídeo
specs/           especificações com critérios de aceite
reference/       código base de TSP da FIAP, sem alterações
tests/           testes unitários e de integração
```

## Documentação

- [Arquitetura](docs/arquitetura.md), com diagramas Mermaid, e [ADRs](docs/adr/)
- [Do TSP ao VRP](docs/do-tsp-ao-vrp.md): o que mudou em relação ao código base
- [Fontes da frota e das coordenadas](docs/fontes-frota.md)
- [Prompts](docs/prompts.md) e [avaliação da LLM](reports/avaliacao-llm/resumo.md)
- [Baselines](src/medroute/baselines/README.md) e [especificações](specs/)
- [`PLANEJAMENTO.md`](PLANEJAMENTO.md): cronograma, divisão do trabalho e status

## Equipe (Grupo 42)

Luis Eduardo Ouro Conrado · Beatriz Honey · Pedro Henrique Klein de Almeida · Rodrigo Edson
Fernandes · Alexandre Akio Ogata

## Histórico das rodadas

A rodada S3 de 23/10 é a fonte dos resultados acima e do relatório. As anteriores ficam como registro:
`reports/comparativo-s1/` (09/10, fitness provisório), `reports/comparativo-s1-atualizado-van/` e
`reports/comparativo-s2/` (19/10, dados reais e trânsito, base da avaliação da LLM). Análises em
[`reports/secoes/pedro-baselines-s1.md`](reports/secoes/pedro-baselines-s1.md) e
[`reports/secoes/pedro-savings-runner-s2.md`](reports/secoes/pedro-savings-runner-s2.md).
