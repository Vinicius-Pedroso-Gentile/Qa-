# Tarefa 3 — Conexão com o browser remoto

> Pré-requisito: leia `00-contexto.md` e o `PROGRESSO.md`. As tarefas 1 e 2 já estão prontas.

## Objetivo

Conectar via **CDP** (`connect_over_cdp`) no Chromium que **outro servidor** abriu, achar a
página certa, reconectar quando a conexão cair e **isolar uma sessão por requisição**, para
que duas requisições não pisem uma na outra.

Esta tarefa entrega o **objeto de sessão** em que as tarefas 4 e 7 vão trabalhar. Ela não
lê o DOM nem executa ações de teste.

---

## Contexto: o que muda em relação à POC

Na POC, o próprio serviço fazia `chromium.launch()` e havia **um browser global** para o
servidor inteiro. Aqui é diferente:

| POC | Serviço novo |
|---|---|
| O serviço abre o browser | O browser **já está aberto** em outro servidor |
| Um browser global | Várias sessões, cada uma com o seu browser/página |
| `browser.close()` no fim | **Nunca** fechar o que não é nosso. Só desconectar |
| Estado em variáveis do módulo | Estado por `session_id` |

O estado de conversa que a POC guardava na sessão **continua necessário** e precisa
sobreviver entre requisições da mesma sessão:
- `elements`: o inventário mais recente da página (tarefa 4);
- `active_form`: o formulário em que o usuário está trabalhando, usado para desempatar
  campos repetidos (tarefa 5);
- `last_element`: o último elemento em que o agente mexeu, para "apague isso" saber de
  qual campo se trata (tarefa 5).

---

## O que fazer

### 1. Contrato de entrada

Veja a decisão **D3** no contexto. Até ela ser confirmada, use este formato e deixe
anotado como **[CONFIRMAR]** no `PROGRESSO.md`:

```python
class BrowserTarget(BaseModel):
    session_id: str                 # identifica a conversa/teste do lado de quem chama
    cdp_url: str                    # ex.: "http://host:9222" ou "ws://host:9222/devtools/browser/<id>"
    page_target_id: str | None = None   # o mais preciso, quando o outro servidor souber
    page_url: str | None = None         # alternativa: a página cuja URL começa com esta
    page_index: int | None = None       # último recurso
```

### 2. Pool de conexões (`app/browser/connection.py`)

- **Uma** instância de `async_playwright()` para o processo, iniciada no `lifespan` do
  FastAPI e parada no desligamento.
- Conexões reaproveitadas por `cdp_url`: `await pw.chromium.connect_over_cdp(cdp_url, timeout=...)`.
  Conectar a cada requisição custa caro; reaproveite enquanto `browser.is_connected()`.
- Escute `browser.on("disconnected")` para tirar a conexão do pool. A próxima requisição
  reconecta sozinha.
- **Reconexão**: se uma operação falhar porque a conexão caiu, reconecte **uma vez** e
  tente de novo. Se falhar de novo, devolva um erro claro
  (`BrowserUnavailableError("Não consegui conectar no browser em <host>")`, sem credenciais
  da URL).
- No desligamento do serviço, **desconecte** sem fechar páginas nem contextos do outro
  servidor. Verifique na documentação do Playwright o comportamento de `close()` em um
  browser obtido por `connect_over_cdp` e escolha a forma que **não derruba** o browser
  remoto. O teste de aceite abaixo prova isso.

### 3. Achar a página certa

Com o browser conectado, procure a página em **todos** os contextos existentes
(`browser.contexts` → `context.pages`), nesta ordem:

1. `page_target_id`: compare com o target id da página (obtenha via CDP, por exemplo com
   `context.new_cdp_session(page)` e `Target.getTargetInfo`);
2. `page_url`: a primeira página cuja URL começa com o valor informado;
3. `page_index`: a posição na lista;
4. nenhum dos três: se houver **uma única** página, use ela. Se houver várias, erro
   `"Há N páginas abertas; informe qual usar"` listando as URLs.

**Não crie página nova** se não achar a pedida. Devolva erro: quem abre páginas é o outro
servidor.

### 4. Sessão por requisição (`app/browser/session.py`)

```python
class AgentSession:
    """Uma página remota + o que o agente sabe dela. Vive entre requisições do mesmo session_id."""
    session_id: str
    page: Page
    elements: list[PageElement]      # preenchido pela tarefa 4
    active_form: str = ""
    last_element: PageElement | None = None

    @property
    def current_url(self) -> str: ...
    @property
    def is_open(self) -> bool: ...
```

- Um **registro em memória** `session_id → AgentSession`, com expiração por inatividade
  (ex.: 30 min) para não vazar memória.
- **Um `asyncio.Lock` por `session_id`**: duas requisições da mesma sessão executam **em
  fila**, nunca ao mesmo tempo na mesma página. Sessões diferentes rodam em paralelo.
- Se a página da sessão foi fechada ou trocou (o outro servidor navegou ou fechou a aba),
  procure de novo pelo `BrowserTarget` e **zere** o inventário, o `active_form` e o
  `last_element`.
- Exponha um context manager para as próximas tarefas usarem:

```python
async with sessions.acquire(target) as session:
    ...  # aqui só esta requisição mexe nesta página
```

### 5. Rota de diagnóstico

`POST /sessao/conectar` recebendo um `BrowserTarget` e devolvendo:

```json
{ "ok": true, "session_id": "abc", "url": "https://bugbank.netlify.app/", "pages": 2 }
```

Ela serve só para testar a conexão nesta sprint. A rota principal do agente vem depois.

---

## Fora do escopo

- Ler o DOM e montar o inventário (tarefa 4).
- Executar ações (tarefa 7).
- Transmitir a tela (screencast).
- Abrir ou fechar páginas no browser remoto.

---

## Critérios de aceite

Para os testes, suba um Chromium local com `--remote-debugging-port=9222` como se fosse o
"outro servidor" (um fixture do pytest que faz `launch(args=[...])` ou um processo à parte)
e abra o BugBank nele.

- [ ] Conecta pela `cdp_url` e acha a página por `page_url`, por `page_index` e,
      quando houver uma só, sem nenhum dos dois.
- [ ] Com duas páginas abertas e nenhum seletor de página, devolve o erro listando as URLs.
- [ ] Depois de encerrar o serviço (ou a sessão), o browser "remoto" **continua aberto**,
      com as mesmas páginas.
- [ ] Derrubando e subindo o browser remoto de novo, a próxima requisição reconecta sozinha.
- [ ] Duas requisições simultâneas no mesmo `session_id` executam em sequência. Teste com
      uma operação lenta e meça a ordem.
- [ ] Duas sessões diferentes rodam em paralelo.
- [ ] Sessão inativa além do tempo limite sai do registro.
- [ ] Nenhum log mostra credenciais embutidas na `cdp_url`.
- [ ] `PROGRESSO.md` atualizado, com o formato do `BrowserTarget` marcado como [CONFIRMAR] se D3 ainda estiver aberta.
