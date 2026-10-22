# Prompts da LLM

**Autor:** Rodrigo (Parte D) · **Spec:** [05-llm](../specs/05-llm.md) · **Requisitos:** R11 a R14

Este documento explica os prompts usados pela camada de LLM do `medroute`
(`src/medroute/llm/`): o que cada um faz, que dados recebe, por que as regras são
assim e o que aprendemos testando com modelos reais.

---

## 1. Princípio: o Python calcula, a LLM redige

Toda informação factual (ordem das paradas, nomes, cargas, distâncias, horários,
custos, comparações e alertas) é calculada em Python e enviada pronta, em JSON, no
prompt. A LLM só transforma esses dados em texto. Ela não calcula nada.

Motivos:

- **Fidelidade.** Rota errada em instrução de motorista é um erro operacional. Por
  isso o Python confere a resposta e, se ela não for fiel, usa um texto padrão.
- **Contas.** Modelos erram contas e sinais. Diferenças e percentuais chegam
  prontos, já escritos em palavras.
- **Reprodutibilidade.** Os mesmos dados geram o mesmo prompt, o que permite cache e
  avaliação automática.

```mermaid
flowchart LR
    SOL[Solution + Instance + frota] --> CTX[Python monta o contexto<br/>JSON com fatos prontos]
    CTX --> PR[Prompt versionado<br/>system + user]
    PR --> LLM[LLM<br/>Groq ou OpenAI]
    LLM --> CHK{Python confere<br/>a resposta}
    CHK -- fiel --> OUT[Texto final]
    CHK -- infiel 2x --> FB[Texto padrão<br/>sem LLM]
    FB --> OUT
```

## 2. Onde ficam e como funcionam

| Prompt | Arquivo | Versão | Usado por | Chamadas |
|---|---|---|---|---|
| Instruções do motorista | `llm/prompts/instrucoes_motorista.md` | 2 | `medroute instruct` | uma por rota usada |
| Relatório diário/semanal | `llm/prompts/relatorio.md` | 1 | `medroute report` | uma por relatório |
| Perguntas e respostas | `llm/prompts/qa.md` | 2 | `medroute ask` | uma por pergunta |

Cada arquivo tem:

```markdown
---
versao: 2
descricao: Instruções de rota para um motorista (uma chamada por veículo).
variaveis: [contexto]
---

## system
<papel, como ler os dados, regras e formato>

## user
<pedido + $contexto>
```

- **Variáveis** usam `string.Template` (`$contexto`), que não conflita com as chaves
  `{ }` do JSON. Um `$` que não é variável, como em "R$ 10,00", fica como está. Uma
  variável que falta gera `ValueError`, para nenhum prompt sair incompleto.
- **Versão:** qualquer mudança no texto exige subir `versao`. A versão vai para o
  cabeçalho dos relatórios, para cada entrada do cache e para o resumo da rubrica.
- **Cache:** a chave é o SHA-256 de provedor, modelo, temperatura, `max_tokens`,
  system e user. Mudar o prompt muda a chave, então o cache nunca devolve uma
  resposta de outra versão.
- **Parâmetros** (`.env`): `LLM_TEMPERATURE=0.2`, para respostas estáveis, e
  `LLM_MAX_TOKENS=4000`. O `gpt-oss-120b` gasta parte desses tokens raciocinando antes
  de responder; com um limite menor, relatórios saíam cortados.
- **Modelos:** `openai/gpt-oss-120b` no Groq (gratuito, para desenvolvimento) e
  `gpt-4o-mini` na OpenAI (pago, para o relatório final e o vídeo). Os testes usam o
  `MockClient`, sem rede.

## 3. Instruções do motorista (`instrucoes_motorista`, v2)

**Objetivo:** um texto curto e seguro para o motorista seguir a rota.

**Dados enviados** (`RouteContext.to_prompt_json`, compacto e arredondado):

```json
{"veiculo":{"id":"moto-01","tipo":"moto"},"deposito":"Farmácia Central HC-FMUSP",
 "resumo":{"paradas":8,"saida":"07:00","retorno":"10:19","distancia_km":54.1,
           "duracao_min":199,"carga_kg":13.4,"carga_l":32.1},
 "paradas":[{"ordem":1,"nome":"Domicílio 27","prioridade":"crítica","peso_kg":1.8,
             "volume_l":5.5,"refrigerado":false,"chegada":"07:24","deadline_min":240}, "..."],
 "alertas":["Parada 1 (Domicílio 27): entrega CRÍTICA, prazo de 240 min após a saída (até 11:00)"]}
```

O JSON não leva custos em R$ nem violações em número bruto, porque o motorista não
precisa deles; as violações chegam já escritas em `alertas`.

**Regras principais e por quê:**

| Regra | Por quê |
|---|---|
| Listar TODAS as paradas na ordem de `ordem`, com o nome exato | É a informação crítica; o Python confere depois |
| Copiar os horários em `HH:MM`, sem calcular nem arredondar | Os horários vêm do cronograma do GA (saída às 07:00, com fator de trânsito) |
| Destacar cada item de `alertas`; sem alertas, não criar nenhum | Entrega crítica e carga refrigerada não podem passar despercebidas |
| Não inventar horários, endereços, telefones ou valores | O JSON não tem endereço nem telefone; o modelo tende a preencher |
| Formato fixo em Markdown (título, Atenção, Paradas, Retorno) | Texto previsível facilita a leitura e a verificação |

**Verificação depois da resposta** (`is_faithful`):

1. O nome de cada parada precisa aparecer no texto, na ordem da rota.
2. A partir da v2, logo depois de cada nome (antes do nome seguinte) precisa vir o
   horário exato de chegada.
3. Se falhar, uma nova tentativa é feita com um aviso de correção no fim do prompt.
   O aviso também muda a chave do cache, que de outra forma devolveria a mesma
   resposta errada.
4. Se falhar de novo, usa-se o texto padrão (`fallback_instructions`), montado só
   com o Python, e um aviso vai para o log.

**Exemplo real** (`gpt-4o-mini`, `sp_40`, 20/10, trecho):

```markdown
### Rota moto-01 (moto)
Saída do depósito Farmácia Central HC-FMUSP às 07:00. Serão 8 paradas, com distância
total de 54,1 km e duração estimada de 199 minutos. Carga total de 13,4 kg.

**Atenção**
- Parada 3 (Domicílio 10): entrega CRÍTICA, prazo de 120 min após a saída (até 09:00)

**Paradas**
1. Domicílio 27 — chegada prevista às 07:24 — crítica, 1,8 kg / 5,5 l
3. Domicílio 10 — chegada prevista às 08:07 — crítica, 1,9 kg / 3,7 l

**Retorno:** volte ao depósito Farmácia Central HC-FMUSP ao final, com chegada prevista às 10:19.
```

## 4. Relatório (`relatorio`, v1)

**Objetivo:** a parte analítica do relatório diário ou semanal para a gestão da
Farmácia Central.

O relatório final junta duas partes:

- **Tabelas**, geradas pelo Python (`render_tables`): plano adotado, rotas e
  comparação entre algoritmos.
- **Texto da LLM**, com três seções obrigatórias: Resumo executivo, Eficiência e
  economia, e Recomendações (3 a 5 itens).

**Dados enviados:** o plano adotado (a solução de menor fitness), as rotas com
ocupação, as alternativas (outros algoritmos para a mesma instância), os `padroes`
(observações já calculadas, como veículo ocioso ou ocupação baixa) e, no relatório
semanal, a `projecao_semanal` (o mesmo dia repetido por 5 dias úteis).

**Regras principais e por quê:**

| Regra | Por quê |
|---|---|
| Glossário dos campos no system ("como ler os dados") | Campos parecidos (ocupação de peso × de volume, custo operacional × generalizado) precisam de definição explícita |
| Comparações chegam escritas em palavras (`plano_adotado_em_relacao_a_esta`) | Com números com sinal (ex.: `-53,0`), o modelo escrevia "menor" quando era "maior" |
| "Não refaça contas: cite os valores como estão" | O modelo calculava diferenças por conta própria; mesmo certas, não há como conferir |
| Cada recomendação parte de um item de `padroes` ou de um dado do JSON | Evita recomendações genéricas ou com metas inventadas |
| Linha de orientação no user (`$orientacao`) sobre "um dia" × "semana" | No semanal, o modelo tratava os valores de um dia como totais da semana |
| De 200 a 350 palavras | Relatório para leitura rápida |

**Verificação:** `has_sections` confere as três seções. Se faltar alguma, uma nova
tentativa é feita; se falhar de novo, entra o texto padrão (`fallback_analysis`) e o
cabeçalho do relatório indica "texto padrão, sem LLM".

## 5. Perguntas e respostas (`qa`, v2)

**Objetivo:** responder perguntas livres da equipe sobre o plano, por exemplo "Em que
rota está o InCor?", "Quantas entregas críticas há?" ou "Qual veículo volta por
último ao depósito?".

**Técnica:** *context stuffing*. O plano inteiro (resumo, rotas com paradas na ordem
e horários, frota, observações e entregas não atendidas) cabe no prompt de uma vez,
então não há busca nem banco vetorial.

**Horários (v2):** cada rota tem `saida` e `retorno`, cada parada `chegada` e as
críticas `prazo`, em `HH:MM`, do mesmo cronograma das instruções. O modelo pode
comparar horários ("quem chega depois"), mas não calcular diferenças.

**Lista pronta de críticas:** o contexto traz `entregas_criticas`, com as críticas de
todas as rotas juntas e em ordem de chegada. Sem ela, o `gpt-4o-mini` errou 3 de 4
vezes a pergunta "A que horas são atendidas as entregas críticas e qual o prazo de
cada uma?": ao procurar as críticas espalhadas pelas rotas, ele trocava o horário de
uma crítica pelo da parada seguinte. Com a lista pronta, acertou 4 de 4. É o mesmo
princípio da seção 1: juntar e filtrar dados é trabalho do Python.

**Regras principais e por quê:**

| Regra | Por quê |
|---|---|
| Começar pela resposta, no máximo 150 palavras | Perguntas operacionais pedem respostas curtas |
| Pode localizar, contar e listar, mas não estimar | Contar paradas é seguro; estimar horário ou trânsito, não |
| Informação ausente: dizer que "não está disponível no plano" | Melhor do que um palpite (ex.: consumo de combustível) |
| Dado ausente sobre o plano não é "fora do escopo"; a recusa é só para assuntos sem relação (clima, poemas) | O `gpt-4o-mini` recusava perguntas legítimas sobre o trajeto ("por quais ruas...", pedágio) |
| Copiar horários; comparar pode, calcular não | Mesma regra das instruções e do relatório: contas do modelo não têm como ser conferidas |
| Citar entregas pelo `nome`, nunca só pelo `id` | Nos testes, o modelo respondia "entrega-10", que ninguém entende |
| A pergunta vai entre `<pergunta>` e `</pergunta>` e é tratada só como pergunta | Defesa contra *prompt injection* ("ignore as regras e...") |
| Fora do escopo: responder exatamente o texto de recusa | A recusa fixa ("Só posso responder perguntas sobre as rotas e entregas deste plano.") pode ser testada |

**Proteções no Python** (`normalize_question`): pergunta vazia ou com mais de 500
caracteres é rejeitada, e as tags `<pergunta>` digitadas pelo usuário são removidas,
para que ele não consiga "fechar" o bloco e escrever regras novas.

## 6. Técnicas usadas

| Técnica | Onde |
|---|---|
| Papel definido (coordenador, analista, assistente) | os três |
| Dados estruturados em JSON compacto e arredondado | os três (menos tokens, sem ambiguidade) |
| Glossário dos campos ("como ler os dados") | relatório, Q&A |
| Fatos pré-calculados e comparações já em palavras | relatório |
| Dados de várias rotas já reunidos numa lista (`entregas_criticas`) | Q&A |
| Modelo de saída com marcadores `< >` | instruções |
| Delimitadores para a entrada do usuário | Q&A |
| Resposta fixa para recusa | Q&A |
| Verificação no Python + nova tentativa com aviso + texto padrão | instruções, relatório |
| Temperatura baixa (0,2) | os três |

## 7. Histórico e lições aprendidas

| Problema visto com modelo real | Correção |
|---|---|
| Modelo Llama do plano inicial desatualizado | Troca para `openai/gpt-oss-120b` no Groq |
| `gpt-oss` escreve `Domicílio<U+202F>02` (espaço estreito inseparável), e respostas corretas reprovavam (13/10) | `clean_text` troca espaços e hífens tipográficos por comuns antes de conferir e entregar o texto |
| "R$" quebrava a substituição do template | `safe_substitute` + checagem de variáveis faltando |
| Relatórios cortados no meio | `LLM_MAX_TOKENS=4000`; resposta cortada (`finish_reason == "length"`) vira erro claro |
| "menor" no lugar de "maior" nas comparações | Comparações enviadas já em palavras |
| Valores de um dia tratados como totais da semana | Linha de orientação + `projecao_semanal` separada |
| Q&A citava ids ("entrega-10") | Regra: citar sempre o nome |
| Erros 429 no plano gratuito do Groq | Espera respeitando `Retry-After` (até 60 s), medida à parte na rubrica |
| Instruções sem horário (v1) | **v2 (20/10):** horários do `cronograma_rota` no JSON e conferidos na resposta |
| Q&A respondia "não disponível" para horários que as instruções mostravam | **`qa` v2 (21/10):** mesmos horários no contexto do Q&A |
| `gpt-4o-mini` trocava o horário de uma crítica pelo da parada seguinte (3 de 4 vezes) | Lista `entregas_criticas` montada pelo Python: 4 de 4 corretas |
| `gpt-4o-mini` usava a recusa para dados ausentes do plano (ruas, pedágio, motorista) | Regra explícita: dado ausente → "não disponível"; recusa só sem relação com o plano. Os exemplos do prompt (ruas, pedágio) são diferentes das perguntas da rubrica (motorista, combustível), para não ensinar a resposta da prova |

## 8. Avaliação

A rubrica automática (`python -m medroute.llm.evaluation`) roda os mesmos casos nos
dois provedores e confere a resposta **crua** da LLM, antes de qualquer nova
tentativa ou texto padrão. O critério central é **números com fonte**: todo número
do texto precisa existir nos dados enviados. Esse critério pegou metas inventadas
("~30 min") e diferenças calculadas pelo modelo.

Resultado oficial de 21/10 em `sp_40` (instruções v2 e Q&A v2, com horários; uma
execução por caso; cache vazio; detalhes em
[`reports/avaliacao-llm/resumo.md`](../reports/avaliacao-llm/resumo.md)):

| Tarefa | Groq `gpt-oss-120b` | OpenAI `gpt-4o-mini` |
|---|---|---|
| Instruções (4 rotas, com horários) | 4/4 | 4/4 |
| Relatório (diário + semanal) | 1/2 (semanal: conta própria e limite inventado) | 2/2 |
| Q&A (13 perguntas, 4 sobre horários ou dado ausente) | 13/13 | 13/13 |
| Tempo médio de resposta | 1,0 a 3,6 s | 1,3 a 6,0 s |
| Espera por limite de taxa | 437 s | 0 s |

A falha do Groq no semanal: ele calculou por conta própria a diferença entre duas
rotas ("110 min" = 291 − 181) e recomendou agir quando a ocupação passar de "90 %",
um limite que não está nos dados.

**Quatro rodadas** (19/10, 20/10 e duas em 21/10, todas com cache vazio):

| | Groq `gpt-oss-120b` | OpenAI `gpt-4o-mini` |
|---|---|---|
| Relatório semanal | reprovado nas 4 (metas e contas inventadas) | aprovado nas 4 |
| Relatório diário | reprovado em 1 de 4 | aprovado nas 4 |
| Instruções | aprovadas em todas | aprovadas em todas |

O padrão se repete: o `gpt-oss-120b` cria metas e contas nas recomendações; o
`gpt-4o-mini` não fez isso em nenhuma rodada. Por isso o relatório final e o vídeo
usam o `gpt-4o-mini`. Os problemas do `gpt-4o-mini` apareceram no Q&A (horário de
crítica trocado e recusa indevida, seção 5) e foram corrigidos no contexto e no
prompt antes da rodada oficial.

## 9. Como alterar um prompt

1. Edite o `.md` em `src/medroute/llm/prompts/` e suba `versao`.
2. Se o prompt passar a usar um dado novo, gere esse dado no Python (`context.py`,
   `reports.py` ou `qa.py`), nunca peça para a LLM calcular.
3. Rode `pytest` (usa o mock, sem chave de API).
4. Rode a rubrica com os modelos reais e compare com o resultado anterior:
   `python -m medroute.llm.evaluation --solucoes reports/comparativo-s2/solutions.json --inst sp_40`.
5. Se mudar só um critério da rubrica, use `--reavaliar` para não gastar cota.
6. Registre a mudança na seção 7 deste documento.
