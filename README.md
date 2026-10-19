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
medroute demo
```

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
```

`instruct` e `report` usam o `LLM_PROVIDER` do `.env` (`--provedor mock` roda sem rede). O `report` aceita
uma ou mais `Solution` ou o `solutions.json` do `compare`; com várias instâncias, `--inst` escolhe uma.

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
