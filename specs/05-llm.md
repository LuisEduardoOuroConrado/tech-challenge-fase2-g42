# Spec 05 — Camada de LLM (instruções, relatórios e Q&A)

- **Responsável:** Rodrigo Edson Fernandes
- **Status:** Rascunho em 06/10/2026 · aguardando revisão
- **Revisor:** a definir
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
    def complete(self, system: str, user: str) -> str: ...

class MockClient:
    """Determinístico e sem rede. Devolve '[mock]\n' + user e registra as chamadas."""
    provider = "mock"
    model = "mock"
    calls: list[tuple[str, str]]
    def complete(self, system: str, user: str) -> str: ...

class OpenAICompatibleClient:
    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        timeout_s: float = 60.0,
        max_retries: int = 3,
        sdk_client: OpenAI | None = None,   # injeção para testes sem rede
    ) -> None: ...
    def complete(self, system: str, user: str) -> str: ...

def client_from_env(env: Mapping[str, str] | None = None) -> LLMClient: ...

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

def build_route_contexts(solution: Solution, inst: Instance) -> list[RouteContext]: ...

# llm/prompts.py
def load_prompt(nome: str) -> Prompt: ...  # lê llm/prompts/<nome>.md

# llm/instructions.py  (P0 — S1)
def generate_instructions(
    solution: Solution,
    inst: Instance,
    client: LLMClient,
) -> dict[str, str]: ...                 # vehicle_id -> texto em Markdown

# llm/reports.py  (P0 — S2)
def generate_report(
    solutions: list[Solution],
    inst: Instance,
    periodo: Literal["diario", "semanal"],
    client: LLMClient,
) -> str: ...

# llm/qa.py  (P1 — S3)
def answer(question: str, solution: Solution, inst: Instance, client: LLMClient) -> str: ...
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
3. Erros transitórios (limite de taxa 429, timeout, falha de conexão) são
   repetidos até `max_retries` vezes com espera exponencial (2 s, 4 s, 8 s).
   Esgotadas as tentativas ou em erro não transitório (ex.: 401), lança `LLMError`.
4. Resposta vazia é tratada como erro (`LLMError`).
5. A chave de API nunca aparece em logs, mensagens de erro ou arquivos de cache.
6. O módulo não carrega `.env` sozinho; quem chama (CLI/Streamlit) chama
   `load_dotenv()` (`python-dotenv`, já nas dependências) antes de `client_from_env`.

### Contexto (Solution + Instance)

1. Toda entrega de `Route.sequence` deve existir em `Instance.deliveries`; caso
   contrário, `ValueError` indicando o ID.
2. `solution.instance_nome` deve ser igual a `inst.nome`; caso contrário, `ValueError`.
3. A ordem das paradas é exatamente a de `Route.sequence`, numerada a partir de 1.
4. Rotas com `sequence` vazia são ignoradas (veículo não usado).
5. O contexto é serializado para o prompt como JSON compacto, com números
   arredondados (km e kg em 1 casa, R$ em 2), para economizar tokens.

### Prompts

1. Cada prompt fica em `llm/prompts/<nome>.md`, com um cabeçalho de versão
   (`versao: 1`) e as seções `system` e `user`. Templates usam `string.Template`
   (`$variavel`) para não conflitar com as chaves do JSON.
2. Prompts são versionados no Git; mudar o texto exige incrementar `versao`.
   Saídas e avaliações registram a versão usada (R14).
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
5. Horários de chegada por parada ficam fora da S1; entram quando a Spec 03 P1
   (`cronograma_rota`) estiver disponível.

### Relatórios (S2)

1. Métricas (custo total, km, nº de veículos, entregas por prioridade, violações,
   comparação entre algoritmos quando há mais de uma `Solution`) são calculadas
   em Python e passadas prontas à LLM.
2. A LLM redige: resumo executivo, eficiência e economia, e uma seção
   "Recomendações" baseada nos padrões dos dados (R13).

### Cache (S2)

1. Respostas de provedores reais são gravadas em `LLM_CACHE_DIR/<hash>.json`.
2. O hash é SHA-256 de `provider`, `model`, `temperature`, `max_tokens`, `system`
   e `user`. Mesma entrada → mesma resposta sem nova chamada à API.
3. O `MockClient` não usa cache. O diretório não é versionado.

### Q&A (S3, P1)

1. *Context stuffing*: o contexto completo da solução vai no prompt junto com a
   pergunta.
2. Pergunta fora do escopo das rotas recebe uma recusa curta e educada.

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
  sobre a fixture com Groq e revisar o texto.

## Cronograma

| Até | Entrega |
|---|---|
| 09/10 (S1) | `client.py` (mock + Groq/OpenAI), `context.py`, `prompts/instrucoes_motorista.md`, `instructions.py` + testes → libera `medroute instruct` (Alexandre) |
| 16/10 (S2) | `reports.py` com recomendações, cache, uso real do Groq → libera `medroute report` |
| 23/10 (S3) | `qa.py` (`medroute ask`), rubrica de avaliação Groq × gpt-4o-mini, `docs/prompts.md` |

## Decisões pendentes

1. **Marcador de teste `llm_real`:** registrar em `pyproject.toml`
   (`--strict-markers` está ativo).

## Fora de escopo

- Cálculo de rotas, custos, horários e violações (Specs 02 e 03).
- Outros provedores (ex.: Claude/Anthropic, Gemini); se necessário, entram como
  nova implementação de `LLMClient` com ADR própria.
- Streaming de respostas, *function calling* e RAG.
- Tradução para outros idiomas.
- Envio das instruções aos motoristas (e-mail, WhatsApp etc.).
