# Tech Challenge Fase 2 — G42 · Planejamento (Spec-Driven)

**Projeto escolhido:** Projeto 2 — Otimização de Rotas para Distribuição de Medicamentos e Insumos
("caixeiro viajante médico" → VRP com frota heterogênea) + LLM para instruções, relatórios e Q&A.

**Repositório (novo):** <https://github.com/LuisEduardoOuroConrado/tech-challenge-fase2-g42>
**Grupo:** mesmo da Fase 1 — Luis Conrado · Beatriz Honey · Pedro Henrique Klein · Rodrigo Edson Fernandes · Alexandre Akio
**Nome do pacote Python:** `medroute`

> Status deste documento: **v0.2 — decisões de arquitetura fechadas (ADRs 0001–0005 em `docs/adr/`)**.
> Itens marcados com [PENDENTE] ainda dependem do grupo e são tratados na seção 11. Os já fechados estão marcados com [FECHADO].

---

## 1. O que o enunciado exige (checklist de nota)

Extraído do PDF "IADT - Fase 2 - Tech challenge". Tudo abaixo é **obrigatório** para o Projeto 2:

| # | Requisito | Onde atendemos |
|---|-----------|----------------|
| R1 | Representação genética adequada para rotas | `ga/encoding.py` (permutação + decoder) |
| R2 | Operadores especializados: seleção, crossover, mutação | `ga/operators.py` (torneio, OX/PMX, swap/inversion/2-opt) |
| R3 | Fitness com distância, prioridade e outras restrições | `ga/fitness.py` (custo generalizado em R$) |
| R4 | Restrição: prioridades (crítico × regular) | `constraints/priority.py` |
| R5 | Restrição: capacidade limitada de carga | `constraints/capacity.py` |
| R6 | Restrição: autonomia limitada (distância máxima) | `constraints/autonomy.py` |
| R7 | Múltiplos veículos (VRP) | decoder *giant-tour → split* |
| R8 | Outras restrições interessantes | deadline p/ críticos, compatibilidade carga×veículo, jornada máx. |
| R9 | Visualizar rotas otimizadas em mapa | `viz/map.py` (folium → HTML) |
| R10 | Partir do **código base de TSP fornecido** e modificá-lo | seção 4.1 — relatório deve mostrar o "antes × depois" |
| R11 | LLM: instruções detalhadas para motoristas | `llm/instructions.py` |
| R12 | LLM: relatórios diários/semanais (eficiência, economia) | `llm/reports.py` |
| R13 | LLM: sugerir melhorias com base em padrões | `llm/reports.py` (seção "recomendações") |
| R14 | LLM: prompts eficientes | `llm/prompts/*.md` versionados + avaliação |
| R15 | LLM: responder perguntas em linguagem natural sobre rotas | `llm/qa.py` |
| R16 | Projeto Python bem estruturado + ambiente virtual (Poetry, Pipenv ou venv) | venv + `requirements.txt` + `requirements.lock` + `pyproject.toml` |
| R17 | Documentação detalhada **com diagramas de arquitetura** | `docs/arquitetura.md` (Mermaid) |
| R18 | Testes automatizados | `tests/` com pytest + GitHub Actions |
| R19 | Relatório técnico: GA, restrições, LLM, **comparativo com outras abordagens**, visualizações | `reports/tech-challenge-fase2-grupo42.pdf` |
| R20 | Vídeo ≤ 15 min: sistema rodando, componentes, resultados GA, demo LLM | YouTube não listado |
| Opc | Nuvem / IaC | **fora do escopo** (pontuação extra, não vale o custo) |

ATENCAO: **Pendência imediata:** baixar o código base de TSP na plataforma da FIAP e commitar em `reference/tsp_base/`
(intocado) para que o relatório evidencie o que foi modificado.

---

## 2. Decisões de escopo [FECHADO] (ver ADRs 0001–0005)

Princípio: **complexidade em camadas**. P0 = obrigatório para a nota; P1 = recomendado (diferencia o trabalho
e cabe no prazo); P2 = só se sobrar tempo. Nada de P2 entra na `main` antes de P0 e P1 estarem prontos e testados.

### 2.1 Frota — número e tipo de veículos (moto, carro, van) → **INCLUIR (P0)**

Frota heterogênea é o que dá sentido a capacidade, autonomia e custo. Parâmetros iniciais (configuráveis em
`configs/frota.yaml`, valores são hipóteses plausíveis — a justificar no relatório):

| Tipo | Qtd | Capacidade | Autonomia | Vel. média urbana | Custo/km | Custo fixo/dia | Restrições |
|------|:---:|:----------:|:---------:|:-----------------:|:--------:|:--------------:|-----------|
| Moto | 2 | 15 kg / 40 L | 120 km | 35 km/h | R$ 0,80 | R$ 60 | não leva carga refrigerada nem volumosa |
| Carro | 2 | 150 kg / 400 L | 300 km | 28 km/h | R$ 1,50 | R$ 120 | — |
| Van | 1 | 800 kg / 3000 L | 400 km | 24 km/h | R$ 2,50 | R$ 200 | — |

O GA **não** é obrigado a usar todos os veículos: o custo fixo penaliza acionar um veículo a mais. O número de
veículos disponíveis é entrada do problema (não é gene).

### 2.2 Capacidade → **INCLUIR (P0, obrigatório)**

Cada entrega tem `peso_kg` e `volume_l`. Restrição *hard* tratada por penalidade alta no fitness
**e** pelo decoder (que abre nova rota ao estourar capacidade). Duas camadas: o decoder evita a maioria das
violações; a penalidade garante que as restantes sejam eliminadas pela seleção.

### 2.3 Custo monetário no fitness → **INCLUIR (P0)**

Decisão-chave: **o fitness é um custo generalizado em R$** (minimizar). Isso evita o problema clássico de
"somar km com prioridade" e deixa o comparativo com baselines trivial de explicar no relatório:

```
fitness(solução) =
    Σ_veículos [ custo_fixo_v · usado_v  +  custo_km_v · dist_v ]           # custo operacional
  + Σ_entregas [ peso_prioridade_i · tempo_chegada_i · R$/min ]            # prioridade (críticos chegam antes)
  + P_cap  · Σ_v max(0, carga_v − capacidade_v)                            # capacidade
  + P_aut  · Σ_v max(0, dist_v − autonomia_v)                              # autonomia
  + P_dead · Σ_i∈críticos max(0, tempo_chegada_i − deadline_i)             # deadline (P1)
  + P_inc  · nº de entregas em veículo incompatível                        # compatibilidade (P1)
  + P_jor  · Σ_v max(0, duração_v − jornada_máx)                           # jornada 8h (P1)
```

Pesos de prioridade: `critica=0,50`, `alta=0,15`, `normal=0,05` R$/min (proporção 10 : 3 : 1, calibrada na Spec 03).
Penalidades hard com fixo de R$ 1.000 por rota violada + parte proporcional, para que violar nunca compense.
Todos os pesos ficam em `configs/fitness.yaml` e a sensibilidade a eles é um dos experimentos.

### 2.4 Restrição de TEMPO → **INCLUIR versão simplificada (P1)**; janelas de tempo completas (VRPTW) → **NÃO (P2)**

- INCLUIR (P1): tempo de viagem = distância / velocidade do veículo + tempo de serviço (10 min/parada, `servico_min_padrao` em `configs/frota.yaml`). Cria a noção
  de `tempo_chegada_i`, necessária para prioridade e deadline.
- INCLUIR (P1): **deadline só para entregas críticas** (ex.: "chegar em até 90 min"). Soft constraint (penalidade).
- INCLUIR (P1): jornada máxima por veículo (8 h). Soft.
- NÃO INCLUIR (P2): janelas de tempo `[início, fim]` para todas as entregas. Muda operadores e decoder, dobra a
  complexidade do GA e dos testes. Só se P0+P1 estiverem prontos com folga.

### 2.5 Restrição de VIA (ruas reais / trânsito / zonas) → **modelo simplificado (P1)**; roteamento real → **opcional (P2)**

- INCLUIR (P0): distância **haversine × fator de tortuosidade** (1,3 para carro/van, 1,2 para moto) — aproxima
  distância viária sem depender de internet. Determinístico e testável.
- INCLUIR (P1): **fator de trânsito por período** (manhã 1,4 · tarde 1,2 · noite 1,0) aplicado à velocidade.
  Barato e vira um bom insight para a LLM ("saia às 6h").
- OPCIONAL (P2): matriz real via OSRM (servidor público, com cache em `data/cache/`) só para (a) distâncias reais e
  (b) desenhar o traçado das ruas no mapa. Bônus visual forte para o vídeo, mas com dependência externa.
- OPCIONAL (P2): zona de restrição de circulação (ex.: van proibida no centro em horário comercial — inspirado na
  ZMRC de SP). Modelável como incompatibilidade veículo×entrega por período. Simples e "realista para o
  contexto hospitalar" — bom candidato a R8 se sobrar tempo.

### 2.6 Resumo das camadas

| Camada | Conteúdo | Meta |
|--------|----------|------|
| **P0** | GA TSP → VRP frota heterogênea; capacidade; autonomia; prioridade; custo R$; mapa folium; baselines; LLM instruções+relatório; testes; CLI | Semana 3 |
| **P1** | Tempo de viagem + deadline críticos + jornada; compatibilidade carga×veículo; fator de trânsito; Q&A LLM; Streamlit; 3+ experimentos GA; avaliação da qualidade da LLM | Semana 4 |
| **P2** | OSRM real; zonas de restrição; VRPTW; OR-Tools como baseline extra | Se sobrar |

---

## 3. Domínio e dados [FECHADO]

**Cenário:** hospital universitário em São Paulo com depósito central (farmácia/almoxarifado do HC) que
distribui para (a) unidades da rede (InCor, ICESP, IPq, HU-USP, UBSs…) e (b) atendimento domiciliar.

**Instância padrão** (`data/instancias/sp_40.json`, gerada por `medroute gen` com `seed=17`):
- 1 depósito + **40 entregas** (10 unidades com coordenadas reais + 30 domicílios sintéticos em raio de 15 km);
- por entrega: `id, nome, lat, lon, peso_kg, volume_l, prioridade{critica,alta,normal}, refrigerado, deadline_min?`;
- mix: ~15 % críticas, ~25 % altas, 60 % normais; ~10 % refrigeradas.

Instâncias adicionais para experimentos: `sp_15` (rápida, testes), `sp_80` (estresse). Formato JSON validado
por Pydantic; qualquer pessoa gera novas instâncias sem mexer no código.

---

## 4. Arquitetura

### 4.1 Do código base ao sistema

```
Código base TSP (FIAP)                    medroute
──────────────────────                    ────────
lista de cidades (x, y)          →        Instance {depot, deliveries[], fleet[]}  (Pydantic)
distância euclidiana             →        DistanceMatrix (haversine × tortuosidade | OSRM)
cromossomo = permutação          →        permutação de entregas (giant tour) + decoder split → rotas por veículo
fitness = 1/distância            →        custo generalizado em R$ (seção 2.3)
seleção/crossover/mutação        →        torneio · OX/PMX · swap/inversion/2-opt (mantidos, adaptados)
plot matplotlib/pygame           →        folium (mapa HTML) + matplotlib (convergência)
```

Manter o código base **intocado** em `reference/tsp_base/` e documentar cada mudança em
`docs/do-tsp-ao-vrp.md` — isso vira uma seção do relatório (R10).

### 4.2 Diagrama de componentes

```mermaid
flowchart LR
    subgraph Entrada
        CFG[configs/*.yaml] --> LOAD
        INST[data/instancias/*.json] --> LOAD[data.loader]
    end
    LOAD --> DM[data.distance\nDistanceMatrix]
    LOAD --> GA
    DM --> GA[ga.engine\nGeneticAlgorithm]
    GA --> DEC[ga.decoder\ngiant-tour → rotas]
    DEC --> FIT[ga.fitness]
    CONS[constraints.*] --> FIT
    GA --> SOL[(Solution JSON)]
    BASE[baselines.*\nNN · 2-opt · Savings] --> SOL
    SOL --> VIZ[viz.map / viz.plots]
    SOL --> LLM[llm.*\ninstruções · relatório · Q&A]
    LLMC[llm.client\nOpenAI | Groq | Mock] --> LLM
    VIZ --> APP[app.cli / app.streamlit]
    LLM --> APP
```

### 4.3 Estrutura do repositório

```
tech-challenge-fase2-g42/
├─ README.md · PLANEJAMENTO.md · pyproject.toml · requirements.txt · .env.example
├─ specs/                     # spec-driven: 1 arquivo por módulo (seção 6)
├─ docs/  arquitetura.md · do-tsp-ao-vrp.md · adr/ · prompts.md
├─ configs/  frota.yaml · fitness.yaml · ga_default.yaml · experimentos/*.yaml
├─ data/  instancias/ · cache/ · resultados/
├─ reference/tsp_base/        # código fornecido pela FIAP, sem alterações
├─ src/medroute/
│  ├─ domain/models.py        # Delivery, Vehicle, Depot, Instance, Route, Solution
│  ├─ data/  loader.py · generator.py · distance.py
│  ├─ constraints/  capacity.py · autonomy.py · priority.py · deadline.py · compatibility.py
│  ├─ ga/  encoding.py · operators.py · decoder.py · fitness.py · engine.py
│  ├─ baselines/  nearest_neighbor.py · two_opt.py · savings.py
│  ├─ experiments/  runner.py · metrics.py
│  ├─ viz/  map.py · plots.py
│  ├─ llm/  client.py · instructions.py · reports.py · qa.py · evaluation.py · prompts/*.md
│  └─ app/  cli.py (typer) · streamlit_app.py
├─ tests/  unit/ · integration/ · fixtures/
├─ notebooks/  01_demo_completa.ipynb · 02_experimentos_ga.ipynb
└─ reports/  tech-challenge-fase2-grupo42.pdf · figuras/
```

### 4.4 Stack

Python 3.11 · **venv + `requirements.txt`** (decidido — o enunciado aceita Poetry, Pipenv ou venv; mantemos o
padrão da Fase 1, com `requirements.lock` gerado por `pip freeze` na S0 para travar versões) · `numpy` `pandas` `pydantic` `pyyaml` · `folium` `matplotlib` · `typer` `rich` ·
`streamlit` (P1) · `openai` (API compatível: OpenAI e Groq — estratégia mista, seção 11.2; modo `mock` sem rede para
testes) · `pytest` `pytest-cov` `ruff` · GitHub Actions (lint + testes em cada PR).

---

## 5. Contratos entre módulos (o que permite trabalhar em paralelo)

Estes tipos ficam em `domain/models.py` e são **congelados na Semana 1**. Mudança = PR próprio + aviso no grupo.

```python
class Priority(str, Enum): CRITICA = "critica"; ALTA = "alta"; NORMAL = "normal"
class VehicleType(str, Enum): MOTO = "moto"; CARRO = "carro"; VAN = "van"

class Delivery(BaseModel):
    id: str; nome: str; lat: float; lon: float
    peso_kg: float; volume_l: float
    prioridade: Priority; refrigerado: bool = False
    deadline_min: float | None = None          # minutos após saída do depósito (só críticas)

class Vehicle(BaseModel):
    id: str; tipo: VehicleType
    capacidade_kg: float; capacidade_l: float; autonomia_km: float
    velocidade_kmh: float; custo_km: float; custo_fixo: float
    aceita_refrigerado: bool = True

class Instance(BaseModel):
    nome: str; depot: Depot; deliveries: list[Delivery]; fleet: list[Vehicle]

class Route(BaseModel):
    vehicle_id: str; sequence: list[str]        # ids das entregas, na ordem
    distancia_km: float; duracao_min: float; carga_kg: float; carga_l: float; custo: float
    violacoes: dict[str, float]                 # {"capacidade": 0.0, "autonomia": 12.3, ...}

class Solution(BaseModel):
    instance_nome: str; algoritmo: str; routes: list[Route]
    fitness: float; custo_operacional: float; distancia_total_km: float
    penalidades: dict[str, float]; historico_fitness: list[float]; tempo_exec_s: float; seed: int

# Assinaturas-chave
DistanceMatrix.dist(a_id, b_id) -> float          # km
DistanceMatrix.time(a_id, b_id, vehicle) -> float # min
decode(chromosome: list[str], inst, dm) -> list[Route]
evaluate(routes, inst, weights) -> tuple[float, dict]   # fitness, penalidades
GeneticAlgorithm(inst, dm, config).run(seed) -> Solution
solve_nearest_neighbor(inst, dm) -> Solution     # mesma assinatura para todo baseline
render_map(solution, inst) -> folium.Map
generate_instructions(solution, inst, client) -> dict[vehicle_id, str]
generate_report(solutions: list[Solution], periodo) -> str
answer(question: str, solution, inst, client) -> str
```

`Solution` serializa para JSON em `data/resultados/` — **é a única interface entre GA/baselines e a camada de
LLM/visualização**. Rodrigo e Alexandre podem começar com um `Solution` fake antes do GA existir.

---

## 6. Processo spec-driven [FECHADO] (nível "contratos entre módulos", ADR 0006)

Por que existe: cinco pessoas em paralelo com módulos interdependentes. Sem um contrato prévio, todo mundo
espera o GA ficar pronto ou cada um inventa seu formato e a integração vira retrabalho no final (como a
unificação de notebooks da Fase 1). A spec é uma página que define *o que* o módulo expõe antes de codar *como*.

**Regras:**

1. **Spec formal só onde há interface entre duas pessoas** — domínio/dados, GA, fitness e LLM. Baselines,
   visualização e app são consumidores finais: seguem direto com testes + README do módulo.
2. Conteúdo da spec (`specs/NN-<modulo>.md`, ~1 página): objetivo · interface pública (assinaturas) ·
   regras de negócio · critérios de aceite (Dado/Quando/Então) · testes obrigatórios · fora de escopo.
3. **Spec aprovada = PR revisado por 1 pessoa** (1 dia). Só então começa a implementação.
4. **`domain/models.py` congelado na S0** e um `Solution` de exemplo em `tests/fixtures/solution_sp15.json`.
   Mudança só via PR próprio com aviso no grupo. Isso sozinho entrega a maior parte do benefício.
5. **PR de código só mergeia se:** CI verde · testes cobrindo os critérios de aceite · README/docs do módulo
   atualizados · 1 aprovação.
6. **Decisões viram ADR** (`docs/adr/000N-titulo.md`, ~10 linhas: contexto, decisão, alternativas, consequências).
7. **Branch:** `feature/<parte>-<descricao>` → PR para `main`. `main` sempre roda `medroute demo`.

Specs iniciais (Semana 0/1):

| Spec | Responsável | Tipo |
|------|-------------|------|
| `01-domain-e-dados.md` | Beatriz | formal |
| `02-ga-core.md` (encoding, operadores, decoder, engine) | Conrado | formal |
| `03-fitness-e-restricoes.md` | Conrado + Beatriz | formal |
| `05-llm.md` | Rodrigo | formal |
| Baselines e experimentos | Pedro | README do módulo + testes |
| Viz, app e entrega | Alexandre | README do módulo + testes |

---

## 7. Divisão do grupo (5 integrantes) [FECHADO]

Mesma lógica da Fase 1: cada um dono de uma parte, testes da própria parte incluídos; Alexandre integra.

| Parte | Responsável | Entrega | Principais arquivos |
|-------|-------------|---------|---------------------|
| **A — Arquitetura e núcleo GA** | **Luis Conrado** | Modelos de domínio (com Beatriz); encoding; operadores (torneio, OX, PMX, swap, inversion, 2-opt); decoder giant-tour→split; engine com elitismo e critério de parada; fitness em R$; `docs/do-tsp-ao-vrp.md` | `domain/`, `ga/`, `docs/adr/` |
| **B — Domínio, dados e restrições** | **Beatriz Honey** | Gerador de instâncias (seed), loader/validação, `DistanceMatrix` (haversine×tortuosidade, trânsito P1, OSRM P2), módulos `constraints/*` (capacidade, autonomia, prioridade, deadline, compatibilidade), `configs/*.yaml` | `data/`, `constraints/`, `configs/` |
| **C — Baselines e experimentos** | **Pedro Henrique Klein** | Nearest Neighbor, NN+2-opt, Clarke-Wright Savings (VRP), aleatório; runner de experimentos (≥3 configs do GA × 5 seeds); métricas, tabelas e gráficos de convergência; análise estatística; seção "comparativo" do relatório | `baselines/`, `experiments/`, `notebooks/02` |
| **D — LLM** | **Rodrigo Edson Fernandes** | `LLMClient` (OpenAI/Groq + mock); prompts versionados; instruções por motorista; relatório diário/semanal com recomendações; Q&A sobre `Solution` (context stuffing + funções de consulta); rubrica de avaliação da qualidade (R14); seção LLM do relatório | `llm/`, `docs/prompts.md` |
| **E — Visualização, app, integração e entregáveis** | **Alexandre Akio** | Mapa folium (cores por veículo, ícones por prioridade, popup); gráficos; CLI `typer` (`gen`, `solve`, `compare`, `map`, `instruct`, `report`, `ask`); Streamlit (P1); CI GitHub Actions; testes de integração; `docs/arquitetura.md`; README; PDF; roteiro e edição do vídeo | `viz/`, `app/`, `tests/integration/`, `reports/`, `.github/` |

Todos: testes unitários do próprio módulo, revisão de 1 PR de outra pessoa por semana, texto da própria seção
do relatório, 2–3 min no vídeo.

---

## 8. Cronograma [FECHADO]

**Datas-chave**

| Data | O quê |
|------|-------|
| **28/09 (seg)** | Início — S0 |
| **12/10 (seg)** | Feriado (N. Sra. Aparecida) — S2 tem 4 dias úteis |
| **26/10 (seg)** | Code freeze de funcionalidades: só correções, relatório e vídeo depois disso | — |
| **29/10 (qui)** | **Entrega interna**: PDF final, vídeo publicado, tag `v1.0` | — |
| **30/10 (sex)** | Upload na plataforma FIAP (só publicar; nada novo) | — |
| **03/11 (ter)** | Prazo oficial — 4 dias de folga para imprevistos |

**Sem reuniões.** Toda a coordenação é assíncrona — mensagens no grupo + GitHub:

- **Status semanal (segunda até 12h):** cada um posta no grupo 3 linhas — *fechou* / *vai fechar até sexta* /
  *travado em*. Quem está travado marca a pessoa que desbloqueia.
- **Handoff = PR mergeado + mensagem** no grupo marcando quem depende ("@Rodrigo `Solution` fixture na `main`").
  Sem mensagem, o handoff não aconteceu.
- **Decisões** em issue no GitHub ou ADR (`docs/adr/`); comentários no PR, não no chat, para ficar rastreável.
- **Bloqueio > 24 h sem resposta:** quem está travado segue com a fixture/mocks e registra o risco no status.
- **Fonte de verdade é a `main`:** a `Solution` fixture, os YAMLs e os ADRs mergeados valem mais que qualquer
  mensagem. O `PLANEJAMENTO.md` é atualizado por PR quando algo muda.

### 8.1 Semanas e critérios de pronto

| Semana | Datas | Marco | Critério de pronto (sexta) |
|--------|-------|-------|-----------------------------|
| **S0** | 28/09 – 02/10 | Setup e contratos | `models.py` congelado; `Solution` fixture; specs 01/02/03/05 aprovadas; CI verde; código base FIAP em `reference/`; instância `sp_15` |
| **S1** | 05/10 – 09/10 | TSP funcional | `medroute solve --inst sp_15` gera JSON + mapa; GA vence NN e NN+2-opt; instruções LLM (mock) sobre fixture |
| **S2** | 13/10 – 16/10 | VRP P0 | `sp_40` sem violação hard; frota heterogênea; fitness em R$; Savings; LLM real (Groq); mapa multi-veículo; CLI completa |
| **S3** | 19/10 – 23/10 | P1 | Deadline/jornada/compatibilidade/trânsito; Q&A; Streamlit; experimentos rodados (tabelas + curvas); avaliação LLM |
| **S4** | 26/10 – 29/10 | Entrega | Relatório PDF revisado por todos; vídeo ≤ 15 min publicado; README final; tag `v1.0` |

### 8.1.1 Situação em 08/10 (qui, fim da S1)

- **S0:** fechada (Spec 05 aprovada em 08/10, PR #6; prazo era 02/10) ; código base FIAP em
  `reference/fiap_genetic_algorithm_tsp/` desde 08/10 (R10).
- **S1:** `medroute solve --inst sp_15` gera JSON + mapa ✅ · instruções LLM (mock) sobre a fixture ✅ ·
  **"GA vence NN e NN+2-opt" bloqueado**: baselines do Pedro ainda não estão na `main` (prazo 09/10).
- **Adiantado:** `sp_40`/`sp_80` (Beatriz), decoder giant-tour→split (Conrado), mapa multi-veículo com ícone por
  prioridade (antecipa parte da entrega de 16/10 do Alexandre).
- **Atenção para a S2 (4 dias úteis):** `constraints/` P0 da Beatriz até 14/10 é o próximo elo do caminho
  crítico. O fitness definitivo e o split ótimo já existem (08/10) com `cronograma_rota`/`custo_prioridade`
  provisórios em `ga/fitness.py`, a trocar pelo `constraints/`.
- **LLM:** modelo padrão do Groq passou a ser `openai/gpt-oss-120b` (Llama 3.3 70B descontinuado — ver 11.2).

### 8.2 Handoffs — quem entrega o quê, para quem, até quando

A regra: a data é o **último dia** para entregar sem atrasar quem depende. Entregar antes libera o outro antes.

| Até | Quem | Entrega | Desbloqueia | Status (08/10) |
|-----|------|---------|-------------|----------------|
| **30/09 (qua)** | Conrado | `domain/models.py` congelado + `tests/fixtures/solution_sp15.json` (Solution de exemplo feito à mão) | **todos** — Rodrigo (prompts), Alexandre (mapa), Pedro (métricas) começam sobre a fixture | ✅ 28/09 |
| **30/09 (qua)** | Alexandre | Esqueleto do repo (`src/medroute`, `tests/`, `requirements.txt`, `pyproject.toml`, GitHub Actions rodando `pytest` + `ruff`) | todos abrem PR com CI | ✅ 28/09 (feito por Conrado) |
| **02/10 (sex)** | Beatriz | Loader + gerador + instância `sp_15` + `DistanceMatrix` haversine×fator + `configs/frota.yaml` | Conrado (GA em dados reais na S1), Pedro (baselines) | ✅ 03/10, PR #2 (+1 dia) |
| **02/10 (sex)** | Conrado, Beatriz, Rodrigo | Specs 01/02/03/05 aprovadas (1 revisor cada) | implementação da S1 | ✅ 01/02/03 aprovadas 05/10; 05 aprovada 08/10 (PR #6) |
| **07/10 (qua)** | Beatriz | Instância `sp_40` (10 unidades reais + 30 sintéticas) | Conrado, Pedro, Alexandre testam em escala real | ✅ 03/10 (adiantado; `sp_80` junto) |
| **09/10 (sex)** | Conrado | GA TSP (1 veículo): encoding, torneio, OX/PMX, swap/inversion, elitismo, `historico_fitness` | Pedro (comparativo), Alexandre (mapa com rota real) | ✅ 05/10, PR #3 |
| **09/10 (sex)** | Pedro | Nearest Neighbor, NN+2-opt, aleatório + `metrics.py` (mesma assinatura `solve_*`) | Conrado (referência de qualidade do GA) | ⏳ nada na `main` |
| **09/10 (sex)** | Rodrigo | `LLMClient` (mock + Groq) + prompt de instruções por motorista funcionando sobre a fixture | Alexandre (`medroute instruct` na CLI) | ✅ 08/10, PR #4 |
| **09/10 (sex)** | Alexandre | Mapa folium básico (1 rota) + CLI `gen` / `solve` / `map` | demo da S1 | ✅ 05/10 (feito por Conrado; mapa já multi-veículo) |
| **14/10 (qua)** | Beatriz | `constraints/` capacidade, autonomia, prioridade (funções puras testadas) | Conrado (fitness P0) | ⏳ |
| **16/10 (sex)** | Conrado | Decoder giant-tour→split + fitness em R$ com penalidades P0 → **VRP funcionando em `sp_40`** | Pedro (experimentos), Rodrigo (Solutions reais), Alexandre (mapa multi-veículo) | 🟡 split ótimo + fitness definitivo no PR de 08/10 (sp_40: 4 veículos, sem violação); falta trocar o stub pelo `constraints/` |
| **16/10 (sex)** | Pedro | Clarke-Wright Savings + `experiments/runner.py` (configs YAML × seeds) | rodada de experimentos na S3 | ⏳ |
| **16/10 (sex)** | Rodrigo | Relatório diário/semanal com recomendações (Groq real) + cache de respostas | Alexandre (`medroute report`) | ⏳ |
| **16/10 (sex)** | Alexandre | CLI completa (`compare`, `instruct`, `report`) + mapa multi-veículo (cor por veículo, ícone por prioridade) | demo da S2 | 🟡 mapa pronto; faltam `compare`/`instruct`/`report` |
| **21/10 (qua)** | Beatriz | `constraints/` deadline, compatibilidade, jornada + fator de trânsito na `DistanceMatrix.time()` | Conrado (fitness P1) | — |
| **21/10 (qua)** | Conrado | Fitness P1 (tempo de chegada, deadline, jornada, compatibilidade) + 2-opt local no GA | Pedro (experimento E5 de sensibilidade), Rodrigo (instruções com horários) | — |
| **21/10 (qua)** | Alexandre | Roteiro do vídeo (quem fala o quê, em quantos minutos) | todos preparam sua fala | — |
| **23/10 (sex)** | Pedro | Experimentos E1–E6 rodados: tabelas (média ± dp, 5 seeds), curvas de convergência, figuras em `reports/figuras/` | relatório (seção comparativo) | — |
| **23/10 (sex)** | Rodrigo | Q&A (`medroute ask`) + rubrica de avaliação aplicada a Groq × gpt-4o-mini | relatório (seção LLM), Streamlit | — |
| **23/10 (sex)** | Alexandre | Streamlit (instância → otimizar → mapa → instruções → pergunta) + testes de integração | vídeo | — |
| **23/10 (sex)** | Conrado | `docs/do-tsp-ao-vrp.md` (antes × depois do código base) + `docs/arquitetura.md` com Mermaid | relatório (seções GA e arquitetura) | — |
| **26/10 (seg)** | **todos** | Texto da própria seção do relatório em `reports/secoes/<parte>.md` · **code freeze** | Alexandre monta o PDF | — |
| **27/10 (ter)** | todos | Gravação do vídeo (cada um grava sua parte, 2–3 min, tela + voz) | Alexandre edita | — |
| **28/10 (qua)** | Alexandre | PDF montado para revisão + vídeo editado (corte) | revisão de todos | — |
| **28/10 (qua)** | todos | Revisão do PDF (comentários até 20h) | versão final | — |
| **29/10 (qui)** | Alexandre | **PDF final, vídeo publicado (não listado), README final, tag `v1.0`** | entrega interna cumprida | — |
| **30/10 (sex)** | Conrado | Upload na plataforma FIAP | — | — |

### 8.3 Carga por integrante

Cada um responde por **~20 % do projeto**; o que muda é *quando* a carga cai. Percentuais abaixo são a fração
do esforço de cada integrante por semana (linhas somam 100 %).

| Integrante | Parte | S0 | S1 | S2 | S3 | S4 | Pico |
|------------|-------|:--:|:--:|:--:|:--:|:--:|------|
| **Conrado** | A — GA | 20 % | 25 % | 30 % | 15 % | 10 % | S2 (decoder + fitness) |
| **Beatriz** | B — dados/restrições | 30 % | 15 % | 25 % | 20 % | 10 % | S0 (dados) e S2 (restrições) |
| **Pedro** | C — baselines/experimentos | 10 % | 25 % | 20 % | 35 % | 10 % | S3 (rodar experimentos) |
| **Rodrigo** | D — LLM | 10 % | 25 % | 25 % | 25 % | 15 % | constante S1–S3 |
| **Alexandre** | E — viz/app/entrega | 20 % | 15 % | 15 % | 20 % | 30 % | S4 (PDF + vídeo) |

Leitura prática: Beatriz e Alexandre são os mais carregados na S0 (ninguém começa sem dados e CI); Conrado
tem o caminho crítico na S1–S2 (tudo depende do GA); Pedro e Rodrigo têm o pico na S3; Alexandre fecha em S4.
Quem estiver leve numa semana revisa PRs de quem está no pico.

### 8.4 Caminho crítico e plano B

`models.py` (30/09) → `sp_15` (02/10) → GA TSP (09/10) → constraints P0 (14/10) → **VRP P0 (16/10)** → experimentos (23/10) → relatório (26/10).

- Se o **VRP P0 atrasar** além de 19/10: Pedro roda experimentos no GA TSP (1 veículo) e Rodrigo/Alexandre
  seguem na fixture; o P1 encolhe (corta trânsito e compatibilidade primeiro).
- Se a **S3 estourar**: corta Streamlit (demo via CLI + notebook) e avaliação LLM vira comparação qualitativa.
- **P2 não entra** em nenhum cenário antes de 26/10 — e depois de 26/10 é code freeze.

---

## 9. Experimentos planejados (Pedro, com apoio de Conrado)

| Exp | Variável | Valores |
|-----|----------|---------|
| E1 | Tamanho da população | 50 · 100 · 200 |
| E2 | Taxa de mutação | 0,01 · 0,05 · 0,15 |
| E3 | Crossover | OX · PMX |
| E4 | Mutação | swap · inversion · 2-opt local |
| E5 | Sensibilidade dos pesos do fitness | custo-puro · equilibrado · prioridade-forte |
| E6 | GA × baselines | NN · NN+2-opt · Savings · aleatório (e OR-Tools se P2) |

5 seeds por configuração; reportar média ± desvio, melhor solução, tempo, curva de convergência,
% de violações. Instâncias `sp_15`, `sp_40`, `sp_80`.

---

## 10. Riscos

| Risco | Mitigação |
|-------|-----------|
| Código base da FIAP diferente do esperado | Baixar em S0; a arquitetura em camadas absorve qualquer formato de entrada |
| Custo/limite da API de LLM | Modo `mock` para testes; Groq free tier ou `gpt-4o-mini`; cache de respostas em `data/cache/llm/` |
| GA não converge em `sp_80` | Elitismo + 2-opt local (memético); limitar experimentos pesados a `sp_40` |
| Escopo crescer (VRPTW, OSRM) | Regra P0→P1→P2; nada de P2 antes de S4 |
| Integração tardia | `Solution` JSON congelado em S0; fixtures fake em `tests/fixtures/` desde S1 |
| Vídeo em cima da hora | Roteiro em S3; gravar por partes (cada um grava a sua) |

---

## 11. Kick-off assíncrono — decisões fechadas e pendências

Não há reunião de kick-off. O plano é comunicado por mensagem no grupo com o PDF `docs/kickoff-pontos-de-decisao-g42.pdf`
e este arquivo entra na `main` via PR. **Cada integrante confirma aprovando o PR** (ou comentando nele) até
**30/09**. Objeção a algo fechado = comentário no PR + ADR novo com a alternativa; não trava o restante.

### 11.0 Já fechado (comunicar; objeção vira ADR novo, não trava o início)

| # | Decisão | Registro |
|---|---------|----------|
| 2 | Cinco decisões de arquitetura: sem VRPTW · sem nuvem · haversine×fator · fitness em R$ · frota fixa de 3 tipos | ADRs 0001–0005 |
| 5 | Cenário: depósito na farmácia central do HC-FMUSP (SP); instância `sp_40` (10 unidades reais + 30 domicílios sintéticos) | seção 3 |
| 6 | Divisão A–E igual à proposta (Conrado GA · Beatriz dados/restrições · Pedro baselines/experimentos · Rodrigo LLM · Alexandre viz/app/entrega) | seção 7 |
| 7 | Spec-driven no nível "contratos entre módulos": spec formal só para domínio, GA, fitness e LLM; `models.py` congelado na S0 | seção 6, ADR 0006 |
| 9 | Streamlit entra no P1; começa só na S3, depois do core | seção 2.6 |
| 10 | Ambiente venv + `requirements.txt` + `requirements.lock`; chaves só em `.env` (ignorado), `.env.example` versionado | seção 4.4, arquivos no repo |

### 11.1 Camadas P0 / P1 / P2 — [PENDENTE] confirmar carga de P1 com cada integrante

As listas estão fechadas (seção 2.6). O que falta é cada um aceitar a **própria** carga de P1 e as datas da
seção 8.2 — a aprovação do PR deste plano vale como aceite. Quem achar pesado comenta no PR propondo rebaixar
um item para P2.

| Camada | Significa | Esforço estimado | Se cortar… |
|--------|-----------|:----------------:|------------|
| **P0** | É o mínimo para a nota: cobre R1–R19 do checklist. **Não é negociável.** | ~60 % do tempo | perde requisito obrigatório |
| **P1** | Compromisso do grupo, entra no relatório e no vídeo. Diferencia o trabalho ("restrições realistas" + Q&A + Streamlit + experimentos). | ~30 % | trabalho fica "básico", mas passa |
| **P2** | **Não é promessa.** Só começa depois de P0+P1 mergeados e testados (S4). Não entra no relatório se não estiver pronto. | ~10 % (se sobrar) | nada — é bônus |

Decisões de arquitetura embutidas — **fechadas** (ADRs 0001–0005):

1. **Sem janelas de tempo completas (VRPTW).** Só deadline para críticos + jornada máxima.
2. **Sem nuvem/IaC.**
3. **Distância haversine × fator** no core; OSRM só como P2 visual.
4. **Fitness em R$** (custo generalizado), não multiobjetivo Pareto/NSGA-II.
5. **Frota fixa de 3 tipos** (moto/carro/van) em YAML; o GA escolhe quais usar, não cria veículos.

### 11.2 Provedor de LLM — [PENDENTE] confirmar quem banca o crédito (estratégia mista já definida)

Estimativa de consumo do projeto inteiro (5 semanas, dev + experimentos + gravação do vídeo):

| Uso | Tokens in / out por chamada | Chamadas no projeto |
|-----|:---------------------------:|:-------------------:|
| Instruções por motorista (JSON da rota + prompt) | ~3 000 / ~600 | ~800 (5 veículos × ~160 execuções) |
| Relatório diário/semanal | ~4 000 / ~1 200 | ~150 |
| Q&A | ~3 000 / ~300 | ~600 |
| Avaliação de qualidade (LLM-as-judge, P1) | ~2 000 / ~200 | ~300 |
| **Total aproximado** | **~6 M in / ~1,2 M out** | **~1 850** |

**Opção A — OpenAI (pago, pré-pago via cartão, sem mensalidade):**

| Modelo | US$/1M in | US$/1M out | Custo estimado do projeto |
|--------|:---------:|:----------:|:-------------------------:|
| `gpt-4o-mini` | 0,15 | 0,60 | **≈ US$ 1,60** (com margem 5×: < US$ 10) |
| `gpt-5-mini` | 0,25 | 2,00 | ≈ US$ 3,90 |
| `gpt-4o` (não precisamos) | 2,50 | 10,00 | ≈ US$ 27 |

Na prática: um crédito pré-pago mínimo (~US$ 5–10, uns R$ 30–60) cobre o projeto inteiro com folga.
Sem limite de requisições relevante, latência estável, ótimo em português. Uma pessoa põe o cartão e distribui
a chave via `.env` (nunca commitada); limite de gasto configurado no painel.

**Opção B — Groq (grátis, sem cartão):**

| Modelo (free tier) | RPM | Tokens/min | Req/dia |
|--------------------|:---:|:----------:|:-------:|
| ~~`llama-3.3-70b-versatile`~~ (descontinuado no Groq, out/2026) | — | — | — |
| `openai/gpt-oss-120b` | 30 | 8 000 | 1 000 |
| ~~`llama-3.1-8b-instant`~~ (descontinuado no Groq, out/2026) | — | — | — |

Limites são **por organização**, não por chave — 5 pessoas dividindo a mesma conta compartilham os 1 000 req/dia.
O gargalo real é **tokens/min**: uma rodada completa (5 instruções + 1 relatório ≈ 20 k tokens) leva 2–3 min
com *backoff* e chamadas sequenciais. Custo: **R$ 0**. Qualidade do Llama 3.3 70B / gpt-oss-120b em português é
boa o suficiente para instruções e relatórios. *Developer tier* (só cadastrar cartão, sem cobrança mínima) libera
10× os limites, e os tokens continuam baratos (Llama 3.3 70B ≈ US$ 0,59 / 0,79 por 1M).

**Descartado — Gemini free:** modelos Flash caíram para ~20 requisições/dia; Flash-Lite tem 500/dia mas é fraco.
Inviável para 5 pessoas desenvolvendo.

**Recomendação:** a API do Groq é compatível com o SDK `openai` (só muda `base_url` e `model`), então o
`LLMClient` suporta os dois sem código extra. Proposta:

- **Padrão no desenvolvimento e nos testes:** `mock` (sem rede) → Groq free (`openai/gpt-oss-120b`; o Llama 3.3 70B foi descontinuado).
  Cada dev cria a própria conta Groq para não dividir a cota.
- **Relatório final e vídeo:** `gpt-4o-mini` com ~US$ 5 de crédito (Conrado), para garantir qualidade e zero
  risco de 429 na hora da gravação. Respostas usadas no vídeo ficam **cacheadas** em `data/cache/llm/`.
- Ambos os provedores documentados no relatório como parte da avaliação de qualidade (R14): comparar
  saídas dos dois modelos com a mesma rubrica é um resultado a mais, quase de graça.

### 11.3 Pendências [PENDENTE] — respondidas por mensagem no grupo ou no PR do plano

| # | Pendência | Quem resolve | Como / até quando |
|---|-----------|--------------|-------------------|
| 1 | Cada integrante confirma a própria carga de P1 e suas datas (8.2) | todos | aprovar o PR do plano até **30/09** |
| 3 | Fontes para justificar os números da frota (frete/km, autonomia, velocidade média CET) — valores atuais ficam até então | Beatriz | PR em `configs/frota.yaml` com as fontes até **07/10** |
| 4 | Quem coloca o cartão na OpenAI (~US$ 5–10, limite de gasto US$ 10 no painel) | Conrado (a confirmar) | mensagem no grupo |
| 10a | Localizar e baixar o código base de TSP fornecido pela FIAP → `reference/tsp_base/` | a nomear (quem achar primeiro avisa no grupo) | PR até **01/10** |
| 10b | ~~Dar acesso de escrita ao repo~~ **feito em 27/09**; cada um testa push em `feature/` e avisa no grupo | todos | push de teste até **30/09** |

Prazo: **fechado** — oficial 03/11, entrega interna **29/10**, upload 30/10 (seção 8).
