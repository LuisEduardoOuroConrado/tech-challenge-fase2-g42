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

Consulte `PLANEJAMENTO.md` para arquitetura, responsabilidades e cronograma.

## Baselines e comparação da S1

Nearest Neighbor, NN + 2-opt e aleatório retornam o mesmo formato `Solution` do
GA. As métricas incluem custo, distância, duração, violações e tempo de execução.

```bash
python scripts/compare_sp15.py
```

O script compara os quatro algoritmos em `sp_15` com uma van e cinco seeds,
salvando soluções JSON, métricas CSV, resumo estatístico e parâmetros em
`data/resultados/comparativo_s1/`. A avaliação usa o fitness provisório atual,
sem custo de prioridade.

Veja [baselines](src/medroute/baselines/README.md),
[métricas e reprodução](src/medroute/experiments/README.md) e
[resultados iniciais](reports/secoes/pedro-baselines-s1.md).
