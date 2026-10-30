# Tarefa 2 — Camada de LLM com vários provedores

> Pré-requisito: leia `00-contexto.md` e o `PROGRESSO.md`. A tarefa 1 já está pronta.

## Objetivo

Criar uma camada que **lê do banco qual provedor, modelo e chave usar** e entrega um modelo
pronto para uma **chamada estruturada**, ou seja, uma decisão restrita a um enum. O serviço
precisa suportar **diversos tipos de modelos sem mudar o código do agente**: trocar de
modelo ou de provedor é só mudar o registro no banco.

Começa com **Claude (Anthropic), OpenAI e Gemini (Google)**. Um provedor novo deve entrar
adicionando **só** a integração dele na fábrica, e nada mais.

---

## Contexto: por que essa camada é desenhada assim

Na POC, a camada de LLM tinha **uma única função pública**, e é esse contrato que o resto
do agente espera:

```python
async def classify(*, system: str, examples: list[tuple[str, str]], user: str,
                   schema: dict, run_name: str) -> dict:
    """Uma decisão restrita. Retorna {} se o modelo não devolver um JSON válido."""
```

- `system`: instruções da decisão.
- `examples`: few-shot, como pares (entrada do usuário, resposta JSON do assistente).
- `user`: a entrada de agora (ex.: `"COMANDO: clique em Acessar"`).
- `schema`: JSON Schema de um objeto cujos campos **só aceitam valores de um enum**.
- `run_name`: nome que aparece no LangSmith (ex.: `"escolher_acao"`).
- **Nunca levanta exceção por resposta ruim**: devolve `{}` e quem chamou decide o fallback.

Mantenha esse contrato. As tarefas 5 e seguintes dependem dele.

O helper que monta o schema também vem da POC:

```python
def enum_schema(**props: Iterable[str]) -> dict:
    """JSON Schema de objeto cujos campos só aceitam valores de listas fechadas."""
    return {
        "type": "object",
        "properties": {k: {"type": "string", "enum": list(v)} for k, v in props.items()},
        "required": list(props),
        "additionalProperties": False,   # exigido pelo modo strict da OpenAI
    }
```

O enum de elementos é **dinâmico**: ele muda a cada página (`["E1", "E2", ..., "E48", "NENHUM"]`).
Por isso o schema é um `dict` montado na hora, e não uma classe Pydantic fixa.

---

## O que fazer

### 1. Configuração no banco

Veja a decisão **D2** no contexto. Se a tabela ainda não existir, proponha este formato e
**confirme com o time antes de criar**:

| coluna | tipo | exemplo |
|---|---|---|
| `id` | pk | |
| `role` | texto | `"classifier"` (para quê o modelo serve. Na próxima sprint entra `"planner"`) |
| `provider` | texto | `"anthropic"`, `"openai"`, `"google_genai"` |
| `model` | texto | nome do modelo **exatamente como o provedor espera** |
| `api_key` | texto | criptografada ou referência a um segredo (ver **D4**) |
| `base_url` | texto, opcional | para proxies ou endpoints compatíveis |
| `temperature` | float | `0` |
| `timeout_s` | float, opcional | sobrepõe o padrão do `.env` |
| `max_retries` | int, opcional | sobrepõe o padrão do `.env` |
| `extra` | json, opcional | parâmetros específicos do provedor |
| `active` | bool | só uma ativa por `role` |

**Não fixe nomes de modelo no código.** Eles vêm do banco.

### 2. Fábrica (`app/llm/factory.py`)

```python
async def get_chat_model(role: str = "classifier") -> BaseChatModel:
    """O modelo configurado no banco para esta função, pronto para uso."""
```

- Leia a configuração ativa para o `role`.
- Use `langchain.chat_models.init_chat_model(model=..., model_provider=..., ...)`. Ele já
  sabe criar Anthropic, OpenAI, Google GenAI e vários outros provedores, e é isso que
  permite um provedor novo entrar só com o pacote instalado e uma linha no banco.
- Se algum provedor precisar de um parâmetro diferente (nome do campo da chave, do timeout
  etc.), trate em **um único mapa** `provider → ajuste de kwargs`, e não com `if` espalhado.
- Passe `temperature`, `timeout`, `max_retries`, `api_key` e `base_url` quando houver.
- **Cache** por `(role, id da config, data de atualização)`: não recrie o cliente a cada
  chamada, mas perceba quando a configuração mudar.
- Configuração inexistente ou provedor desconhecido levanta um erro claro **na hora**
  (`LLMConfigError("Nenhuma configuração ativa para role=classifier")`).
- **Nunca logue a chave.** Nem em mensagem de erro.

### 3. Chamada estruturada (`app/llm/structured.py`)

Implemente o `classify(...)` do contrato acima:

1. Monte as mensagens: `SystemMessage(system)`, depois cada exemplo como
   `HumanMessage(entrada)` + `AIMessage(saída)`, e por fim `HumanMessage(user)`.
2. Use `model.with_structured_output(schema)`. Cada provedor implementa de um jeito
   (tool calling na Anthropic, json_schema na OpenAI, response schema no Gemini). Teste
   os três.
3. **Valide a resposta contra o enum** mesmo com saída estruturada. Se o valor não estiver
   na lista, devolva `{}`.
4. Qualquer falha de parse devolve `{}`, nunca uma exceção.
5. Passe `config={"run_name": run_name}` para o trace ficar legível no LangSmith.
6. Limite a resposta (`max_tokens` pequeno, ~128): a resposta é um JSON de um campo.
7. Se o modelo tiver modo de raciocínio ("thinking"), **desligue** para essas chamadas.
   Ele só adiciona latência para escolher um item de uma lista.

### 4. Timeout, retry e rate limit

- **Timeout** por chamada: o da config, senão `settings.llm_timeout_s`.
- **Retry** com backoff exponencial e jitter, só para erros transitórios: timeout, 429,
  5xx e conexão. **Não** repita em 400, 401 ou 403. Pode usar
  `.with_retry(retry_if_exception_type=..., stop_after_attempt=..., wait_exponential_jitter=True)`
  do LangChain ou `tenacity`.
- **Rate limit**: trate 429 como transitório e respeite o `Retry-After` quando vier.
  Opcional: `InMemoryRateLimiter` do LangChain por provedor.
- Erros que **esgotaram** os retries ou que não são transitórios sobem como uma exceção
  própria (`LLMUnavailableError`, `LLMAuthError`), com mensagem curta e sem a chave. Essa é
  a diferença para o `{}`: `{}` significa "o modelo respondeu algo inválido", e a exceção
  significa "não deu para falar com o modelo".

### 5. Health do LLM

Uma função `llm_health(role)` que faz uma chamada `classify` mínima (ex.: enum `["ok"]`)
e diz se o provedor configurado responde. Acrescente o resultado ao `/health` da tarefa 1
como `"llm": "ok"` ou `"llm": "erro: ..."`, sem derrubar o health inteiro por causa disso.

---

## Fora do escopo

- Os prompts de verdade ("qual ação", "qual elemento"): são da tarefa 5.
- Planejador.
- Modelos locais (Ollama etc.).

---

## Critérios de aceite

- [ ] Com a configuração apontando para **cada um** dos três provedores, `classify` com
      `enum_schema(action=["goto","fill","click"])` e o usuário `"COMANDO: clique em Enviar"`
      devolve `{"action": "click"}`. Teste de integração, marcado, um por provedor.
- [ ] Um enum dinâmico de **60 valores** funciona nos três provedores.
- [ ] Trocar o provedor no banco troca o modelo usado **sem reiniciar** o serviço (no
      máximo no próximo request depois da mudança).
- [ ] Resposta fora do enum, JSON inválido ou resposta vazia → `{}`. Teste unitário com
      um modelo fake.
- [ ] 429 e timeout são repetidos com backoff, e 401 não é repetido. Teste unitário com fake.
- [ ] A chave não aparece em nenhum log nem mensagem de erro. Teste que captura os logs.
- [ ] Adicionar um 4º provedor suportado pelo `init_chat_model` não exige mudar o código,
      só instalar o pacote e inserir a configuração. Descreva no `PROGRESSO.md` como fazer.
- [ ] `PROGRESSO.md` atualizado.
