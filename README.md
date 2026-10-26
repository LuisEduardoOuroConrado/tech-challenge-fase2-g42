# medroute

Otimização de rotas para distribuição de medicamentos e insumos com algoritmo
genético, frota heterogênea e apoio de LLM.

## Ambiente local

Requer Python 3.11.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

No Linux ou macOS, ative o ambiente com `source .venv/bin/activate`.

## Verificação

```powershell
python -m ruff check .
python -m pytest
medroute demo --rapido
```

## Demonstração

```bash
medroute demo                      # sp_40, GA híbrido completo (~2 min), LLM mock
medroute demo --provedor openai    # mesma demo com as respostas reais da LLM (chave no .env)
medroute demo --rapido             # GA reduzido, roda em segundos
```

Roda o fluxo ponta a ponta: GA híbrido + mapa → instruções por motorista → relatório semanal → pergunta em
linguagem natural, e salva tudo em `data/resultados/demo/`. Com `mock` a LLM devolve os fatos que recebeu
em vez de redigir o texto.

O notebook [`notebooks/01_demo_completa.ipynb`](notebooks/01_demo_completa.ipynb) mostra o mesmo fluxo com
as saídas salvas (dados, GA × baselines, resultados oficiais, rotas, convergência, mapa e LLM). Para
executá-lo: `python -m pip install -e ".[notebook]"` e abrir no VS Code (no Jupyter, instale também
`jupyterlab`).

Consulte `PLANEJAMENTO.md` para o cronograma e [`docs/arquitetura.md`](docs/arquitetura.md) para a
arquitetura.

## CLI

```bash
medroute gen                                   # instâncias sp_15, sp_40, sp_80
medroute solve --inst sp_40 --seed 7           # GA híbrido -> data/resultados/*.json + mapa
medroute map data/resultados/sp_40_ga_vrp_s7.json
medroute instruct data/resultados/sp_40_ga_vrp_s7.json          # instruções por motorista (LLM)
medroute compare --config configs/experimentos/s2.yaml --seed 7 # GA × baselines (runner)
medroute report data/resultados/comparativo_s2/solutions.json --inst sp_40 --periodo semanal
medroute ask data/resultados/sp_40_ga_vrp_s7.json "Qual veículo chega mais tarde e por quê?"
medroute app                                   # app Streamlit em http://localhost:8501
```

`instruct`, `report` e `ask` usam o `LLM_PROVIDER` do `.env` (`--provedor mock` roda sem rede). O `report`
aceita uma ou mais `Solution` ou o `solutions.json` do `compare`; com várias instâncias, `--inst` escolhe uma.

## App Streamlit

`medroute app` (ou `streamlit run src/medroute/app/streamlit_app.py`, rodando da raiz do repositório) abre o
fluxo completo numa tela: escolher a instância → otimizar com o GA (ou carregar um JSON salvo em
`data/resultados/`) → métricas, mapa, tabela de rotas e curva de convergência → instruções por motorista,
relatório diário/semanal e perguntas em linguagem natural. O provedor da LLM é escolhido na barra lateral
(`mock` não usa rede; `openai` usa o crédito pré-pago e as respostas ficam em cache).

## Baselines e experimentos (entrega de 16/10)

Nearest Neighbor, NN + 2-opt, Clarke-Wright Savings e aleatório retornam
`Solution`. O runner compara todos com o GA usando o mesmo fitness definitivo,
split, frota e restrições P0/P1.

```bash
python scripts/compare_sp15.py
python scripts/compare_sp15.py --frota-completa
python -m medroute.experiments.runner --config configs/experimentos/s2.yaml
# equivalente, com tabela-resumo: medroute compare --config configs/experimentos/s2.yaml
```

O comparativo S1 atualizado roda GA puro/híbrido e quatro baselines, com cinco
seeds. O YAML da S2 roda três configurações do GA × cinco seeds em `sp_15` e
`sp_40`. Exporta JSON, métricas, resumo, convergência e metadados para
`data/resultados/` (ignorado pelo Git). `--out` escolhe outro destino.

Veja [baselines](src/medroute/baselines/README.md),
[métricas e reprodução](src/medroute/experiments/README.md) e
[entrega e resultados de 16/10](reports/secoes/pedro-savings-runner-s2.md) e
[plano revisado](docs/plano-pedro-1610.md).

A rodada de 09/10 em `reports/comparativo-s1/` permanece como registro histórico
do fitness provisório; os comparativos atualizados ficam em
`reports/comparativo-s1-atualizado-van/` e `reports/comparativo-s2/`.

## Experimentos E1–E6 (entrega de 23/10)

```bash
python -m medroute.experiments.study --workers 4
# Recria tabelas e figuras das soluções salvas, sem otimizar novamente:
python -m medroute.experiments.study --render-only
```

A matriz em [`configs/experimentos/s3.yaml`](configs/experimentos/s3.yaml) cobre
`sp_15`, `sp_40` e `sp_80`, cinco seeds e 300 gerações, com a frota definitiva e
trânsito. São 300 observações e 240 execuções únicas: referências idênticas entre
experimentos são reutilizadas. O cache em `data/resultados/experimentos_s3_cache/`
permite retomar uma execução interrompida; receitas, dados e fontes têm hashes.

Os [resultados e tabelas](reports/experimentos-s3/resumo.md), as
[figuras PNG/PDF](reports/figuras/s3/) e a
[análise para o relatório](reports/secoes/pedro-experimentos-s3.md) são versionados.
O [notebook de análise](notebooks/02_experimentos.ipynb) tem saídas salvas.
E5 inclui a reavaliação sob os pesos oficiais para comparar objetivos diferentes.
O [plano revisado](docs/plano-pedro-2310.md) explica os controles e a escolha do
2-opt local de E4. Tempos foram medidos sob concorrência; cinco seeds fornecem
estatística descritiva, sem teste de significância.

A auditoria registra a contagem duplicada de incompatibilidade presente no
decoder da base em duas soluções inviáveis do aleatório. Os CSVs incluem a
reavaliação por entregas únicas; detalhes e impacto estão na seção do relatório.
