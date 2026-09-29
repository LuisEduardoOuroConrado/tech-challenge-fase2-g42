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