# Spec 05 — Camada de LLM (instruções, relatórios e Q&A)

- **Responsável:** Rodrigo Edson Fernandes
- **Status:** Aprovada em 08/10/2026 (OK do Rodrigo)
- **Revisor:** Conrado (revisão 08/10/2026, sobre o código do PR #4)
- **Escopo:** `src/medroute/llm/`
- **Base:** `domain/models.py`, Spec 01 (dados), Spec 03 (fitness), `.env.example` e
  `PLANEJAMENTO.md` seção 11.2 (provedores)

## Objetivo

O módulo recebe uma `Solution` (saída do GA ou de um baseline) e a `Instance`
correspondente e produz texto legível em português para pessoas: instruções por
motorista, relatórios com recomendações e respostas a perguntas sobre as rotas.

Princípio central: **o Python calcula, a LLM redige.** Todos os fatos (ordem das
paradas, nomes, cargas, distâncias, custos e violações) são montados de forma
determinística a partir de `Solution` + `Instance`. A LLM apenas transforma esses
fatos em texto; ela não reordena paradas, não faz contas e não inventa dados.

## Provedores

| `LLM_PROVIDER` | Uso | Rede | Implementação |
|---|---|---|---|
| `mock` | testes, CI e desenvolvimento offline (padrão) | não | `MockClient` |
| `groq` | desenvolvimento com LLM real (`openai/gpt-oss-120b`) | sim | `OpenAICompatibleClient` + `GROQ_BASE_URL` |
| `openai` | relatório final e vídeo (`gpt-4o-mini`) | sim | `OpenAICompatibleClient` |

Groq e OpenAI usam o mesmo SDK `openai`; muda apenas `base_url`, chave e modelo.
A configuração vem das variáveis de ambiente de `.env.example`.

## Interface pública

```python
# llm/client.py
class LLMError(RuntimeError): ...

class LLMClient(Protocol):
    provider: str
    model: str
    def complete(self, system: str, user: str, *, prompt: Prompt | None = None) -> str: ...

class MockClient:
    """Determinístico e sem rede. Devolve '[mock]\n' + user e registra as chamadas."""
    provider = "mock"
    model = "mock"
    calls: list[tuple[str, str]]
    def complete(self, system: str, user: str, *, prompt: Prompt | None = None) -> str: ...

class OpenAICompatibleClient:
    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        timeout_s: float = 60.0,
        max_retries: int = 3,
        sdk_client: OpenAI | None = None,   # injeção para testes sem rede
        sleep: Callable[[float], None] = time.sleep,  # injeção para testes sem espera
    ) -> None: ...
    def complete(self, system: str, user: str, *, prompt: Prompt | None = None) -> str: ...

def client_from_env(env: Mapping[str, str] | None = None) -> LLMClient: ...

# llm/cache.py  (S2)
class CachedClient:
    """Envolve um LLMClient real e grava cada resposta em <cache_dir>/<hash>.json."""
    inner: LLMClient
    hits: int
    misses: int
    def __init__(self, inner: LLMClient, cache_dir: str | Path) -> None: ...
    def complete(self, system: str, user: str, *, prompt: Prompt | None = None) -> str: ...

# llm/context.py — junção determinística Solution + Instance
class StopContext(BaseModel):
    ordem: int
    id: str
    nome: str
    prioridade: Priority
    peso_kg: float
    volume_l: float
    refrigerado: bool
    deadline_min: float | None
    chegada_min: float | None = None     # minutos após a saída (com frota)

class RouteContext(BaseModel):
    vehicle_id: str
    vehicle_tipo: VehicleType
    deposito: str
    paradas: list[StopContext]
    distancia_km: float
    duracao_min: float
    carga_kg: float
    carga_l: float
    custo: float
    violacoes: dict[str, float]          # apenas as maiores que zero
    saida_min: float | None = None       # minuto do dia da saída (420 = 07:00)

def build_route_contexts(
    solution: Solution, inst: Instance, fleet: FleetConfig | None = None
) -> list[RouteContext]: ...

# llm/prompts.py
def load_prompt(nome: str) -> Prompt: ...  # lê llm/prompts/<nome>.md

# llm/instructions.py  (P0 — S1)
def generate_instructions(
    solution: Solution,
    inst: Instance,
    client: LLMClient,
    fleet: FleetConfig | None = None,    # com frota, traz horários de chegada
) -> dict[str, str]: ...                 # vehicle_id -> texto em Markdown

# llm/reports.py  (P0 — S2)
def generate_report(
    solutions: list[Solution],
    inst: Instance,
    periodo: Literal["diario", "semanal"],
    client: LLMClient,
) -> str: ...

# llm/qa.py  (P1 — S3)
def answer(
    question: str,
    solution: Solution,
    inst: Instance,
    client: LLMClient,
    fleet: FleetConfig | None = None,    # com frota, o contexto traz horários
) -> str: ...
```

Diferença em relação ao `PLANEJAMENTO.md` seção 5: `generate_report` recebe também
`inst` (para nomes das unidades) e `client` (para permitir mock nos testes), igual
às demais funções.

## Regras de negócio

### Cliente

1. `client_from_env` lê `LLM_PROVIDER`; valor ausente equivale a `mock`. Valor
   desconhecido ou chave vazia para `groq`/`openai` geram `LLMError` com mensagem
   que diz qual variável configurar.
2. O modelo vem de `GROQ_MODEL` / `OPENAI_MODEL`; nenhum nome de modelo fica
   fixo no código (modelos são descontinuados — ex.: Llama 3.3 70B no Groq).
   `temperature` e `max_tokens` vêm de `LLM_TEMPERATURE` e `LLM_MAX_TOKENS`.
3. Erros transitórios (limite de taxa 429, timeout, falha de conexão, erro 5xx) são
   repetidos até `max_retries` vezes com espera exponencial (2 s, 4 s, 8 s) ou, se
   maior, a indicada no `Retry-After` do provedor (teto de 60 s): o limite do Groq
   gratuito é por minuto, e 2 + 4 + 8 s não bastavam (visto em 19/10 no Q&A).
   Esgotadas as tentativas ou em erro não transitório (ex.: 401), lança `LLMError`.
4. Resposta vazia é tratada como erro (`LLMError`). Resposta cortada pelo limite
   de tokens (`finish_reason == "length"`) também, mesmo com texto: em modelos
   com raciocínio (`gpt-oss-120b`), `max_tokens` cobre o raciocínio e a resposta.
   Por isso o padrão de `LLM_MAX_TOKENS` é 4000 (o relatório usa ~1.200 a 1.500).
5. A chave de API nunca aparece em logs, mensagens de erro ou arquivos de cache.
6. O módulo não carrega `.env` sozinho; quem chama (CLI/Streamlit) chama
   `load_dotenv()` (`python-dotenv`, já nas dependências) antes de `client_from_env`.

### Contexto (Solution + Instance)

1. Toda entrega de `Route.sequence` deve existir em `Instance.deliveries`; caso
   contrário, `ValueError` indicando o ID.
2. `solution.instance_nome` deve ser igual a `inst.nome`; caso contrário, `ValueError`.
   O mesmo vale para `Route.vehicle_id` que não exista em `Instance.fleet`.
3. A ordem das paradas é exatamente a de `Route.sequence`, numerada a partir de 1.
4. Rotas com `sequence` vazia são ignoradas (veículo não usado).
5. O contexto é serializado para o prompt como JSON compacto, com números
   arredondados (km e kg em 1 casa, R$ em 2), para economizar tokens.
6. O JSON das **instruções** não leva custo em R$ nem violações em valor bruto: o
   motorista não precisa deles, e as violações já viram texto em `alertas`. Custos
   entram só no contexto dos relatórios e do Q&A.

### Prompts

0. Prompts atuais: `instrucoes_motorista` (v2), `relatorio` (v1) e `qa` (v2). Um `$` que não
   inicia variável (ex.: "R$ 10,00") fica como está; variável ausente gera `ValueError`.
1. Cada prompt fica em `llm/prompts/<nome>.md`, com um cabeçalho de versão
   (`versao: 1`) e as seções `system` e `user`. Templates usam `string.Template`
   (`$variavel`) para não conflitar com as chaves do JSON.
2. Prompts são versionados no Git; mudar o texto exige incrementar `versao`.
   Saídas e avaliações registram a versão usada (R14): a partir da S2, a entrada de
   cache guarda `prompt` e `versao`, e o relatório e a rubrica citam a versão.
   `generate_instructions` continua devolvendo só o texto (S1).
3. Todo prompt instrui a LLM a: responder em português do Brasil; usar apenas os
   dados fornecidos; não alterar a ordem das paradas; não inventar horários,
   endereços ou valores; dizer explicitamente quando a informação não existe.

### Instruções por motorista

1. Uma chamada à LLM por rota usada; o resultado é indexado por `vehicle_id`.
2. O texto contém: resumo (veículo, nº de paradas, distância, carga), lista
   numerada de paradas na ordem da rota, alertas e retorno ao depósito.
3. Alertas obrigatórios quando aplicáveis: entrega **crítica** (e seu deadline),
   carga **refrigerada** e qualquer violação maior que zero.
4. **Verificação de fidelidade:** após a resposta, o Python confere se o nome de
   cada parada aparece no texto e na ordem da rota. Se falhar, faz uma nova
   tentativa; se falhar de novo, usa o texto de *fallback* determinístico gerado
   a partir do `RouteContext` (sem LLM) e registra um aviso no log.
   A busca é por trecho de texto (sem diferenciar maiúsculas), então depende de
   os nomes das entregas serem únicos e nenhum estar contido em outro. Isso vale
   para `sp_15`, `sp_40` e `sp_80` (conferido em 08/10); instância nova que quebre
   a regra exige trocar a busca por correspondência com a lista numerada.
   Antes da comparação e da entrega do texto, espaços inseparáveis (U+00A0, U+2007,
   U+202F) viram espaço comum e hífens U+2010/U+2011 viram `-`: o `gpt-oss-120b`
   escreve `Domicílio<U+202F>02`, o que reprovava respostas corretas (visto em 13/10).
   A nova tentativa anexa ao prompt um aviso de correção; isso orienta o modelo e
   muda a chave do cache, que de outra forma devolveria a mesma resposta infiel.
5. **Horários de chegada (prompt v2, 20/10).** Com a frota (`fleet`), o contexto usa
   `cronograma_rota` e `duracao_rota` (Spec 03) com saída em `inicio_jornada` (07:00)
   e o fator de trânsito, como no GA. O JSON ganha `saida` e `retorno` no resumo e
   `chegada` por parada, já em `HH:MM`; o alerta de entrega crítica ganha o prazo
   em relógio ("até 10:00"). O prompt manda copiar os horários sem recalcular.
   A duração vem do mesmo cronograma, para o retorno nunca ficar antes da última
   parada (nas soluções de `sp_40` ela é igual à da `Solution`).
   A fidelidade passa a exigir, depois do nome de cada parada e antes da seguinte,
   o seu horário exato; o *fallback* também traz os horários. Sem frota não há
   horários e tudo funciona como na v1. O comando `instruct` passa a frota de `--frota`.
   O Q&A recebe os mesmos horários a partir do `qa` v2 (seção Q&A, regra 7).

### Relatórios (S2)

1. Métricas (custo total, km, nº de veículos, entregas por prioridade, violações,
   comparação entre algoritmos quando há mais de uma `Solution`) são calculadas
   em Python e passadas prontas à LLM.
2. A LLM redige: resumo executivo, eficiência e economia, e uma seção
   "Recomendações" baseada nos padrões dos dados (R13).
3. `solutions` são planos para a **mesma instância** (ex.: GA e baselines). Fica uma
   solução por algoritmo (a de menor fitness); a melhor de todas é o **plano adotado**
   e as demais entram como alternativas de comparação. As métricas base vêm de
   `experiments/metrics.py` (`extract_metrics`, `improvement_pct`).
4. O relatório final é Markdown: cabeçalho (plano, provedor/modelo, prompt e versão),
   **tabelas geradas em Python** (indicadores, rotas, comparação entre algoritmos e,
   no semanal, projeção) e, por último, o texto da LLM. Os números das tabelas nunca
   passam pela LLM.
5. O custo generalizado é decomposto como na Spec 03: operacional + prioridade
   (`fitness - custo_operacional - penalidades`) + penalidades.
6. **Padrões** calculados em Python alimentam as recomendações: veículos ociosos (com
   o custo fixo), ocupação baixa (< 50%) ou alta (>= 90%) na dimensão mais cheia,
   autonomia >= 80%, entrega crítica na segunda metade da rota, rotas desbalanceadas
   (maior >= 1,5 x menor), violações e a diferença para cada alternativa.
7. **Diferenças vão à LLM em frases prontas** (`"plano adotado 52,3 km maior (30,9%)"`),
   não em números com sinal: com sinal, o `gpt-oss-120b` trocou "maior" por "menor"
   (visto em 13/10). O mesmo vale para a dimensão da ocupação (peso ou volume).
8. **Semanal = projeção:** não há dados de vários dias, então `periodo="semanal"`
   repete o dia por 5 dias úteis com a mesma demanda. A premissa aparece na tabela e
   o prompt separa "por dia" de "estimativa da semana".
9. **Verificação:** o texto da LLM precisa ter os títulos `Resumo executivo`,
   `Eficiência e economia` e `Recomendações`, nessa ordem. Se faltar, nova tentativa
   com aviso; se faltar de novo, texto padrão sem LLM (o cabeçalho informa).
10. Limite conhecido: a verificação não confere cada número do texto da LLM contra os
    dados; isso entra na rubrica de avaliação da S3.

### Cache (S2)

1. Respostas de provedores reais são gravadas em `LLM_CACHE_DIR/<hash>.json`.
2. O hash é SHA-256 de `provider`, `model`, `temperature`, `max_tokens`, `system`
   e `user`. Mesma entrada → mesma resposta sem nova chamada à API.
3. O `MockClient` não usa cache. O diretório não é versionado.
4. `client_from_env` devolve um `CachedClient` para `groq`/`openai` quando
   `LLM_CACHE_DIR` está preenchida; vazia ou ausente desliga o cache.
5. Cada arquivo guarda `provider`, `model`, `temperature`, `max_tokens`, `prompt`,
   `versao`, `criado_em`, `system`, `user` e `response` — nunca a chave de API.
   `prompt` e `versao` vêm do argumento opcional `prompt=` de `complete`.
6. Erros do provedor não são gravados; arquivo ilegível é tratado como ausência
   (aviso no log) e refeito. A gravação é atômica (arquivo temporário + renomear).
7. Para forçar novas respostas, apague o diretório de cache.

### Q&A (S3, P1)

1. *Context stuffing*: o contexto completo da solução vai no prompt junto com a
   pergunta. `build_qa_context` reaproveita `build_report_data` (resumo, ocupação,
   observações) e acrescenta as paradas de cada rota em ordem (com `id` e `nome`) e
   as `entregas_nao_atendidas`. Em `sp_40`, ~7.400 caracteres (~3 mil tokens).
2. Pergunta fora do escopo das rotas recebe uma recusa curta e educada: a frase
   fixa `RECUSA` ("Só posso responder perguntas sobre as rotas e entregas deste
   plano."), que o prompt manda repetir exatamente.
3. A pergunta vai por último, entre `<pergunta>` e `</pergunta>`, e o prompt manda
   tratá-la só como pergunta, nunca como instrução. As tags são removidas do texto
   do usuário antes, para ele não fechar o bloco. Pergunta vazia ou com mais de 500
   caracteres gera `ValueError`.
4. Informação de rota que não está nos dados (ex.: consumo de combustível, nome do
   motorista) recebe "não está disponível no plano", sem estimativa. Isso não é
   "fora do escopo": a recusa fica só para assuntos sem relação com o plano (no `qa`
   v2, porque o gpt-4o-mini recusava "por quais ruas..." e pedágio em 21/10). Contar e listar itens do JSON
   é permitido. Entregas são citadas pelo nome, não só pelo `id`.
5. CLI: `medroute ask <solução.json> "pergunta" [--inst] [--provedor]`. Com várias
   Solutions da instância (ex.: `solutions.json` do `compare`), usa a de menor
   fitness, como o plano adotado do relatório.
6. Testado em 19/10 com Groq sobre `reports/comparativo-s2` (`sp_40`): localização,
   contagem por veículo, custo, horário inexistente, pergunta fora do escopo e
   tentativa de *prompt injection* responderam conforme as regras.
7. **Horários (prompt `qa` v2, 21/10).** Com a frota, o contexto usa o mesmo cronograma
   das instruções: cada rota ganha `saida` e `retorno`, cada parada `chegada` e as
   críticas `prazo`, em `HH:MM`. O prompt manda copiar os horários e permite
   compará-los (quem chega antes ou depois), mas não calcular diferenças.
   `medroute ask` e o Streamlit passam a frota. Sem frota, nada muda.
8. `entregas_criticas`: o Python junta as críticas de todas as rotas numa lista
   (veículo, nome, ordem, prazo e horários), pela ordem de chegada. Sem ela, o
   gpt-4o-mini trocou o horário de uma crítica pelo da parada seguinte em 3 de 4
   tentativas da pergunta "A que horas são atendidas as entregas críticas e qual o
   prazo de cada uma?"; com ela, acertou 4 de 4 (21/10, `sp_40`).

### Avaliação da qualidade (S3, R14)

1. `llm/evaluation.py` roda os mesmos casos em cada provedor e confere a resposta
   **crua** da LLM (antes de nova tentativa ou texto padrão). Uso:
   `python -m medroute.llm.evaluation --solucoes <solutions.json> --inst sp_40
   --provedores groq openai --out reports/avaliacao-llm`.
2. Casos: instruções de cada rota do melhor plano; relatório diário e semanal com
   todos os algoritmos; perguntas de Q&A geradas a partir da própria solução
   (localizar, buscar por id, contar, custo, rota mais longa, explicar custo, dados
   inexistentes, fora do escopo e *prompt injection*). Com a frota são 13: entram
   horário de chegada, último retorno, críticas com horário e prazo, e nome do
   motorista (inexistente) no lugar de "horário inexistente"; sem frota, 10. As
   respostas esperadas saem dos dados, então a rubrica vale se as rodadas oficiais
   forem refeitas.
3. Critérios essenciais: instruções = ordem das paradas, horários (cada parada com o
   seu horário exato; sem frota, igual à ordem), números com fonte e alertas
   citados; relatório = três seções, 3 a 5 recomendações e números com fonte; Q&A =
   comportamento (fatos esperados, "não disponível" ou recusa exata) e números com
   fonte. Informativos: tamanho, tempo, esperas por limite e novas tentativas.
4. **Números com fonte:** todo número do texto precisa existir nos dados enviados,
   com a tolerância do arredondamento escrito; nomes e ids são retirados antes e
   inteiros até 10 passam (contagens). Diferença calculada pelo modelo conta como
   sem fonte, porque o prompt proíbe refazer contas.
5. O tempo do modelo exclui as esperas por limite de taxa, medidas à parte
   (`OpenAICompatibleClient.espera_total_s`). Para medir tempo, rodar com um
   `LLM_CACHE_DIR` vazio; respostas do cache aparecem como "cache".
6. `--reavaliar resultados.json` recalcula a rubrica sem chamar a LLM, mantendo
   respostas e tempos: corrigir um critério não gasta cota.
7. Resultado oficial em `reports/avaliacao-llm/` (21/10, instruções v2 e `qa` v2,
   uma execução por caso; as rodadas anteriores ficam no histórico do Git).
   LLM-as-judge fica fora; a rubrica é determinística e reproduzível.
8. A rubrica carrega a frota de `--frota` (padrão `configs/frota.yaml`), então as
   instruções são avaliadas com horários. Para reavaliar, usar a mesma frota da execução.

## Critérios de aceite

1. **Dado** `LLM_PROVIDER` ausente, **quando** `client_from_env` é chamado,
   **então** retorna um `MockClient`.
2. **Dado** `LLM_PROVIDER=groq` sem `GROQ_API_KEY`, **quando** `client_from_env` é
   chamado, **então** lança `LLMError` citando `GROQ_API_KEY`.
3. **Dada** a fixture `solution_sp15.json` e a instância `sp_15`, **quando**
   `build_route_contexts` é chamado, **então** há 3 rotas, 15 paradas no total, na
   ordem de `sequence`, com nomes e prioridades da instância.
4. **Dada** uma `Solution` com um ID que não existe na instância, **quando** o
   contexto é montado, **então** lança `ValueError` com esse ID.
5. **Dados** a fixture e um `MockClient`, **quando** `generate_instructions` é
   chamado, **então** o resultado tem as chaves `moto-01`, `carro-01` e `van-01` e
   foram feitas exatamente 3 chamadas ao cliente.
6. **Dada** uma rota com entrega crítica ou refrigerada, **quando** o prompt é
   montado, **então** o texto enviado à LLM contém essas marcações.
7. **Dada** uma resposta da LLM que omite uma parada, **quando** a fidelidade é
   verificada duas vezes, **então** o resultado é o *fallback* determinístico, que
   contém todas as paradas na ordem.
8. **Dado** um erro 429 seguido de sucesso, **quando** `complete` é chamado,
   **então** retorna a resposta sem lançar exceção (espera simulada no teste).
9. **Dada** a mesma entrada duas vezes com cache ativo, **quando** `complete` é
   chamado, **então** o SDK é acionado só uma vez (S2).
10. **Dada** uma resposta gravada em cache, **quando** o arquivo é lido, **então**
    ele contém `provider`, `model`, `prompt` e `versao`, e não contém a chave de API (S2).
11. **Dadas** duas `Solution` da mesma instância (ex.: GA e Savings) e um
    `MockClient`, **quando** `generate_report` é chamado, **então** o prompt enviado
    traz as métricas de cada uma já calculadas (custo, km, veículos, violações) e
    o texto final tem a seção "Recomendações" (S2).
12. **Dada** uma pergunta fora do escopo das rotas, **quando** `answer` é chamado com
    um cliente falso que segue o prompt, **então** o prompt enviado contém a regra de
    recusa e a pergunta original (S3).
13. **Dadas** a fixture, a frota e uma resposta da LLM sem os horários de chegada,
    **quando** `generate_instructions` é chamado, **então** o resultado é o *fallback*
    com o horário previsto de cada parada e do retorno (prompt v2).
14. **Dadas** a fixture e a frota, **quando** `build_qa_context` é chamado, **então**
    as paradas têm os mesmos horários de chegada das instruções e
    `entregas_criticas` lista as críticas de todas as rotas pela ordem de chegada (S3).

### Mapa critério → teste (revisão de 08/10)

| Critério | Teste em `tests/unit/llm/` |
|---|---|
| 1 | `test_client.py::test_sem_provedor_usa_mock` |
| 2 | `test_client.py::test_groq_sem_chave_cita_a_variavel` |
| 3 | `test_instructions.py::test_contexto_da_fixture_segue_a_ordem_e_usa_dados_da_instancia` |
| 4 | `test_instructions.py::test_entrega_inexistente_gera_erro_com_o_id` |
| 5 | `test_instructions.py::test_uma_chamada_por_rota_com_mock` |
| 6 | `test_instructions.py::test_prompt_marca_entregas_criticas_e_refrigeradas` |
| 7 | `test_instructions.py::test_resposta_infiel_duas_vezes_usa_fallback` |
| 8 | `test_client.py::test_429_seguido_de_sucesso_tenta_de_novo` |
| 9 | `test_cache.py::test_mesma_entrada_chama_o_provedor_uma_vez` |
| 10 | `test_cache.py::test_arquivo_registra_provedor_modelo_prompt_e_versao` e `::test_arquivo_nao_contem_a_chave_de_api` |
| 11 | `test_reports.py::test_duas_solucoes_com_mock_prompt_traz_metricas_e_texto_tem_recomendacoes` |
| 12 | `test_qa.py::test_pergunta_fora_do_escopo_recebe_recusa_e_prompt_traz_regra_e_pergunta` |
| 13 | `test_instructions.py::test_horario_errado_duas_vezes_usa_fallback_com_horarios` |
| 14 | `test_qa.py::test_com_frota_o_contexto_traz_os_horarios_das_instrucoes` e `::test_criticas_saem_pela_ordem_de_chegada` |

Além dos critérios, já há testes para: veículo inexistente, instância diferente,
rota vazia, JSON arredondado, prompt mal formatado, 401 sem expor a chave, resposta
vazia ou cortada por `max_tokens` e retentativa esgotada.

## Testes obrigatórios

Nenhum teste pode acessar a rede nem exigir chave de API (CI roda com `mock`).

- Cliente: `client_from_env` para cada provedor e para configuração inválida;
  `OpenAICompatibleClient` com SDK falso injetado (sucesso, 429 com retentativa,
  401 sem retentativa, resposta vazia); chave ausente das mensagens de erro.
- Contexto: junção com a fixture, ordem, ID inexistente, instância diferente,
  rota vazia ignorada, violações zeradas omitidas.
- Prompts: carregamento, versão presente, substituição de variáveis com JSON.
- Instruções: uma chamada por rota, chaves corretas, alertas no prompt,
  verificação de fidelidade e *fallback*.
- Relatório e cache (S2); Q&A (S3).
- Teste manual (fora do CI, marcado `@pytest.mark.llm_real`): rodar instruções
  sobre a fixture com Groq e revisar o texto. O marcador está registrado no
  `pyproject.toml` e esses testes ficam fora do `pytest` padrão; rodar com
  `pytest -m llm_real`.

## Cronograma

| Até | Entrega |
|---|---|
| 09/10 (S1) | `client.py` (mock + Groq/OpenAI), `context.py`, `prompts/instrucoes_motorista.md`, `instructions.py` + testes → libera `medroute instruct` (Alexandre) |
| 16/10 (S2) | `reports.py` com recomendações, cache, uso real do Groq → libera `medroute report` |
| 23/10 (S3) | `qa.py` (`medroute ask`), rubrica de avaliação Groq × gpt-4o-mini, `docs/prompts.md` |

## Decisões (fechadas na revisão de 08/10/2026)

1. **Marcador `llm_real`:** registrado no `pyproject.toml` e excluído do `pytest`
   padrão (`-m 'not llm_real'`), para o CI nunca chamar a rede.
2. **Modelo do Groq:** `openai/gpt-oss-120b`, lido de `GROQ_MODEL`; o Llama 3.3 70B
   foi descontinuado (ver `PLANEJAMENTO.md` 11.2). Nenhum nome de modelo fixo no código.
3. **Erros 5xx** contam como transitórios, além de 429, timeout e conexão; o SDK
   roda com `max_retries=0` para as retentativas serem só as nossas.
4. **Instruções sem custo em R$:** o motorista recebe paradas, cargas e alertas;
   custos ficam para relatório e Q&A.
5. **Versão do prompt nas saídas:** registrada a partir da S2 (cache, relatório e
   rubrica); na S1 a versão fica só no arquivo do prompt.
6. **Q&A só com *context stuffing*:** as "funções de consulta" citadas no
   `PLANEJAMENTO.md` (seção 7, parte D) são funções Python que montam o contexto,
   não *function calling* da LLM, que segue fora de escopo.

## Fora de escopo

- Cálculo de rotas, custos, horários e violações (Specs 02 e 03).
- Outros provedores (ex.: Claude/Anthropic, Gemini); se necessário, entram como
  nova implementação de `LLMClient` com ADR própria.
- Streaming de respostas, *function calling* e RAG.
- Tradução para outros idiomas.
- Envio das instruções aos motoristas (e-mail, WhatsApp etc.).
