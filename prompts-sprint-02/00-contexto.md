# Contexto geral — Orquestrador: Serviço de Agente LLM + Playwright

> **Para a IA que vai implementar:** leia este arquivo inteiro antes de qualquer tarefa.
> Ele vale para todos os prompts `01` a `07`. Cada prompt de tarefa assume que você já
> conhece o que está aqui.

---

## 1. O que estamos construindo

Um **serviço em FastAPI** (Python) que funciona como um agente de testes web:

1. **Recebe** os dados de uma sessão do Playwright **que já está aberta em outro servidor**
   e o **prompt do usuário** em linguagem natural (ex.: `"preencha o e-mail com a@b.com"`).
2. **Valida** o que o usuário pediu contra a página real: qual ação é, em qual elemento,
   com qual valor.
3. **Executa** a ação na página via Playwright.
4. **Gera o mapeamento**: a ação, o seletor validado e o código Playwright equivalente.
   Em uma sprint futura isso será salvo no banco e reexecutado **sem LLM**.

O modelo de LLM **não é fixo**. Ele vem de uma configuração no banco (provedor + modelo +
chave). O serviço precisa suportar **diversos provedores**, começando por **Claude
(Anthropic), OpenAI e Gemini (Google)**. Modelos locais estão **fora** do escopo.

### Projeto de referência

Já existe uma POC funcional chamada **Qaí**, com a mesma ideia rodando localmente
(Ollama + qwen3:1.7b + Playwright local + chat web). O serviço novo é uma reescrita **do
zero**, mas as regras, decisões e armadilhas que a POC descobriu estão neste documento e
nos prompts de cada tarefa. **Se o repositório da POC estiver disponível**, ele serve de
referência:

| Arquivo da POC | O que tem de útil |
|---|---|
| `qai/browser.py` | Leitura do DOM, seletores candidatos, validação de unicidade, espera da página estabilizar |
| `qai/interpreter.py` | As duas perguntas para a LLM e as checagens determinísticas |
| `qai/literals.py` | Extração de valores por regex e máscaras em texto esperado |
| `qai/actions.py` | Execução das ações e mensagens de erro |
| `qai/models.py` | `Action`, `Selector`, `PageElement`, `CommandResult`, `Step` |
| `qai/llm.py` | Wrapper de LLM com saída restrita por JSON Schema |
| `DOCUMENTACAO.md` | Explicação linha por linha e o motivo de cada decisão |

**Não copie da POC:** frontend, transmissão de tela (screencast), gravador por clique
(record), blocos, replay de testes salvos e qualquer coisa do Ollama. Nada disso entra
neste serviço.

---

## 2. A arquitetura: fluxo fixo, não agente livre

Esta é a decisão mais importante do projeto. **Não mude sem combinar com o time.**

O agente tem um **fluxo de controle fixo, definido pelo código**. A LLM só preenche
**duas lacunas** dentro dele, e sempre escolhendo de uma **lista fechada**:

```
prompt do usuário: "preencha o e-mail com a@b.com"

  PERCEBER  → lê o DOM da página e monta a lista de elementos reais (E1, E2, E3...)
  DECIDIR   → LLM: "Que ação é?"     (enum: goto | fill | click | expect_text | locate | clear) → fill
              LLM: "Qual elemento?"  (enum: E1 | E2 | ... | NENHUM)                           → E2
  EXTRAIR   → regex recorta o valor "a@b.com" do texto (a LLM NUNCA toca no valor)
  AGIR      → Playwright preenche E2 com "a@b.com"
  PERCEBER  → relê o DOM (a página pode ter mudado)
  RESPONDER → { ok, mensagem, ação, valor, código Playwright do seletor }
```

**Por que não um agente livre** (LLM com ferramentas decidindo sozinha o loop):
- o produto final é um **mapeamento reexecutável**: seletor e valor precisam ser
  confiáveis e iguais em toda execução;
- o modelo vem do banco e pode ser de qualquer provedor. Escolher de uma lista fechada
  funciona igual em todos, enquanto planejar livremente varia muito de modelo para modelo;
- o custo e a latência ficam previsíveis: 2 chamadas curtas por comando.

Um **planejador** (LLM que transforma um objetivo em uma lista de comandos simples) está
previsto para uma sprint futura e **não faz parte desta**.

---

## 3. As três regras (não negociáveis)

Quase toda decisão de código sai de uma destas três:

**Regra 1 — Perguntas pequenas.**
Uma decisão por chamada de LLM, com resposta restrita a um enum. Nunca "o que eu faço
agora?", sempre "isto é `goto`, `fill`, `click`, `expect_text`, `locate` ou `clear`?".
A saída é sempre estruturada (JSON Schema), com temperatura 0.

**Regra 2 — Dado de teste nunca passa pela LLM.**
E-mail, senha, URL e mensagem esperada são **recortados do texto com regex**. Na POC, a
LLM "traduziu" `qualquerCoisa0001@gmail.com` para `anything0001@gmail.com`. Modelos
maiores erram menos, mas o mapeamento salvo não pode ter nem um erro desses.

**Regra 3 — Seletor nunca é inventado.**
A LLM escolhe um **ID de elemento** (`E7`) de uma lista lida do DOM vivo. E, antes de um
elemento entrar nessa lista, o seletor dele é **testado contra a página real** e só é
aceito se resolver para **exatamente aquele elemento**. Alucinação de seletor é
impossível por construção.

---

## 4. Stack

| Camada | Escolha |
|---|---|
| Linguagem | Python 3.11+ |
| API | FastAPI + Uvicorn (async de ponta a ponta) |
| Browser | Playwright **async** (`playwright.async_api`). A API síncrona não funciona dentro de um servidor async |
| LLM | LangChain (`langchain-core`, `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`) |
| Fluxo do agente | LangGraph (só na próxima sprint. Nesta, as peças são funções soltas) |
| Configuração | `pydantic-settings` lendo `.env` |
| Validação de dados | Pydantic v2 |
| Banco | **[PREENCHER: qual banco e como conectar — ex.: PostgreSQL via SQLAlchemy async]** |
| Testes | `pytest` + `pytest-asyncio` |
| Tracing (opcional) | LangSmith, ligado por variável de ambiente |

---

## 5. Estrutura de pastas sugerida

```
orquestrador/
├─ app/
│  ├─ main.py              FastAPI, lifespan, rota /health
│  ├─ config.py            Settings (pydantic-settings)
│  ├─ db.py                conexão com o banco
│  ├─ llm/                 tarefa 2: fábrica de modelos + chamada estruturada
│  ├─ browser/             tarefas 3 e 4: conexão CDP, sessão, inventário, seletores, espera
│  └─ agent/               tarefas 5, 6 e 7: modelos, interpretação, extração, execução
├─ tests/
├─ scripts/                scripts de teste manual (ex.: rodar um comando de ponta a ponta)
├─ .env.example
├─ PROGRESSO.md            o que já foi feito, decisões e pendências (atualizado a cada tarefa)
└─ README.md
```

Pode ajustar, mas mantenha a separação: **llm** não conhece **browser**, e **browser** não
conhece **llm**. Quem junta os dois é **agent**.

---

## 6. Modelos de dados centrais

Todas as tarefas usam estes tipos. Eles nascem na tarefa 4 (`Selector`, `PageElement`) e
na tarefa 5 (`Action`), mas o formato já está decidido aqui:

```python
class Action(str, Enum):
    GOTO = "goto"            # abrir uma URL
    FILL = "fill"            # preencher um campo
    CLICK = "click"          # clicar
    EXPECT_TEXT = "expect_text"  # validar que um texto aparece na tela
    LOCATE = "locate"        # só localizar um elemento, sem interagir
    CLEAR = "clear"          # limpar um campo

    @property
    def needs_element(self) -> bool:
        return self in (Action.FILL, Action.CLICK, Action.LOCATE, Action.CLEAR)


class Selector(BaseModel):
    """Como chegar a um elemento. Estruturado para virar tanto um Locator de verdade
    quanto o trecho de código mostrado ao usuário."""
    kind: Literal["placeholder", "label", "role", "css", "text"]
    value: str
    name: str = ""          # só para kind="role": o nome acessível
    form: str = ""          # escopo no formulário, pelo texto do botão de submit
    nth: int | None = None  # último recurso: fixa a posição
    exact: bool = True      # só para kind="role"

    def to_code(self) -> str: ...   # ex.: "page.get_by_placeholder('Informe seu e-mail', exact=True)"


class PageElement(BaseModel):
    """Um elemento interativo real, lido da página em execução."""
    element_id: str         # "E1", "E2"... válido só até o próximo snapshot
    role: str = ""
    name: str = ""          # o nome que a LLM vê
    input_type: str = ""
    form: str = ""
    editable: bool = False
    selector: Selector

    def describe(self) -> str: ...  # ex.: 'textbox "Informe seu e-mail" [Acessar]'


class CommandResult(BaseModel):
    ok: bool
    message: str            # mensagem curta em português para o usuário
    action: Action | None = None
    value: str = ""
    selector_code: str = "" # o código Playwright equivalente
```

---

## 7. Site de referência para testes

**BugBank** — https://bugbank.netlify.app/

Ele foi usado em toda a POC porque tem as armadilhas reais que o agente precisa vencer:
- os formulários de **login** e de **cadastro** coexistem no DOM, com campos de mesmo nome
  ("Informe seu e-mail") nos dois;
- a troca entre login e cadastro **vira um cartão 3D**, então os campos da face escondida
  continuam com tamanho e `visibility: visible`;
- o modal de resultado fecha em um `<a id="btnCloseModal">` **sem `href`**, que não é um
  `<button>`;
- os cards da home são `<a>` vazios, com o rótulo só no `id` (`id="btn-TRANSFERENCIA"`);
- a tela troca entre 100 ms e 400 ms depois de um clique.

Cenário mínimo de ponta a ponta usado como teste de aceite ao longo da sprint:

```
1. abra https://bugbank.netlify.app/
2. informe o e-mail qualquerCoisa0001@gmail.com
3. informe a senha Teste@123
4. clique em Acessar
5. verifique que a tela exibe "Usuário ou senha inválido. Tente novamente ou verifique suas informações!"
6. clique em Fechar
```

---

## 8. Convenções de código

- **Comentários e docstrings em português, explicando o porquê**, não o quê. Quando um
  trecho existe por causa de um caso real (ex.: "o BugBank faz X"), diga isso no comentário.
- Async em tudo que toca rede, browser ou banco.
- Erros de Playwright **nunca** sobem como stacktrace para o usuário: viram
  `CommandResult(ok=False, message="...")` com uma frase curta.
- Nada de `print`: use `logging`. **Nunca** logue chaves de API nem valores de campos de senha.
- Cada tarefa entrega testes. Testes que precisam de rede ou de browser são marcados
  (ex.: `@pytest.mark.integration`) para poderem ser pulados no CI.

---

## 9. Como trabalhar em cada tarefa

1. Leia este arquivo e o `PROGRESSO.md` do repositório (se existir).
2. Faça **só** a tarefa pedida. Se perceber que algo de outra tarefa é necessário, crie
   a interface mínima e anote no `PROGRESSO.md`, sem implementar a outra tarefa.
3. Se uma decisão marcada como **[PREENCHER]** ou **[CONFIRMAR]** ainda estiver em aberto,
   **pergunte** em vez de assumir.
4. Ao terminar, atualize o `PROGRESSO.md` com:
   - o que foi feito e onde está;
   - decisões tomadas e o motivo;
   - o que ficou pendente;
   - como testar.
5. Confira cada item dos **critérios de aceite** do prompt da tarefa e diga quais passaram
   e quais não passaram.

---

## 10. Decisões em aberto (preencher antes de começar)

| # | Decisão | Valor |
|---|---|---|
| D1 | Banco de dados e forma de conexão | **[PREENCHER]** |
| D2 | A tabela de configuração de LLM já existe? Nome e colunas | **[PREENCHER]** |
| D3 | Como o outro servidor informa a sessão do Playwright: URL CDP/WebSocket? Como identifica a página (target id, URL, índice)? | **[PREENCHER]** |
| D4 | A chave de API fica criptografada no banco? Com qual mecanismo? | **[PREENCHER]** |
