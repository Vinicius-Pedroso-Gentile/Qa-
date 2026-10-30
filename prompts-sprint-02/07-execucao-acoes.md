# Tarefa 7 — Execução das ações

> Pré-requisito: leia `00-contexto.md` e o `PROGRESSO.md`. As tarefas 1 a 6 já estão prontas.

## Objetivo

Executar no Playwright a ação decidida (`goto`, `fill`, `click`, `clear`, `expect_text`,
`locate`) e devolver um `CommandResult` com:
- `ok` e uma **mensagem clara em português**;
- o **valor** usado;
- o **código Playwright equivalente** (`selector_code`), que é o que vai virar o mapeamento.

No fim desta tarefa, um comando em texto roda **de ponta a ponta** na página remota:
interpretar (5) → extrair valor (6) → executar (7).

---

## Princípio: uma implementação só

O despacho de ações fica **fora** de qualquer fluxo de LLM, em uma função que recebe
`(sessão, ação, elemento, valor)`. Assim, na sprint em que o mapeamento salvo for
reexecutado **sem LLM**, ele passa pela **mesma** função. Se o replay tivesse um clique
"um pouco diferente" do clique gravado, a gravação deixaria de valer como prova.

---

## O que fazer

### 1. Ações na sessão (`app/browser/session.py` ou `actions.py` do browser)

Cada ação executa e depois espera a página estabilizar (`settle()` da tarefa 4):

| ação | Playwright | timeout |
|---|---|---|
| goto | `page.goto(url, wait_until="domcontentloaded")` + settle | 60 s |
| fill | `locator(el).fill(valor)` + settle | 15 s |
| clear | `locator(el).fill("")` + settle | 15 s |
| click | `locator(el).click()` + settle | 15 s |
| locate | `locator(el).is_visible()` | 5 s |
| expect_text | `page.get_by_text(alvo).first.wait_for(state="visible")` | 10 s |

`expect_text`: se `to_pattern(valor)` (tarefa 6) devolver uma regex, use a regex. Senão use
o texto literal. O `get_by_text` normaliza espaços, então casa mesmo quando a aplicação
quebra a mensagem em várias linhas, como faz o modal do BugBank. **Não achar o texto é um
resultado (`ok=False`), e não um erro.**

### 2. Despacho (`app/agent/actions.py`)

```python
async def run_action(session, action, element, value) -> CommandResult
async def run_expect_text(session, value) -> CommandResult
```

Regras por ação, todas vindas da POC:

**goto**
- Sem URL → `ok=False`, `"Não reconheci uma URL nesse comando."`
- Depois: `snapshot()`, `active_form = ""`.
- Mensagem: `"Abri <url> — mapeei <N> elementos na página."`
- `selector_code`: `page.goto('<url>')`.

**Ações que precisam de elemento sem elemento** → `ok=False`, `"Preciso abrir uma página antes."`
quando o inventário está vazio. Se o inventário tem itens mas a interpretação não achou
o elemento: `"Não achei esse elemento na página. Disponíveis: "A", "B", ..."` (até 6 nomes).

**fill**
- Sem valor → `ok=False`, `'Entendi que é para preencher "<campo>", mas não achei o valor no comando.'`
- Depois: `snapshot()`, `active_form = element.form`, `last_element = element`.
- Mensagem: `'Preenchi "<campo>" com <valor>'`. Se for campo de senha (`input_type ==
  "password"`), **não** mostre o valor na mensagem nem no log.

**clear**
- Depois: `snapshot()`, `last_element = element`.
- Mensagem: `'Limpei o campo "<campo>"'`.

**click**
- Depois: `snapshot()`, `last_element = element`.
- **`active_form`**: só muda para `element.form` se o elemento clicado **é** o botão de submit
  daquele formulário (`normalize(element.name) == normalize(element.form)`). Senão, vira `""`.
  Motivo: no BugBank, "Registrar" mora **dentro** do formulário de login, mas clicar nele leva
  para o cadastro. Manter "Acessar" como ativo mandaria os próximos campos para a tela errada.
- Mensagem: `'Cliquei em "<nome>"'`.

**locate**
- Não altera a página nem o inventário.
- Se visível: `active_form = element.form`.
- `ok` = visível. Mensagem: `'Encontrei "<nome>" na tela.'` ou `'Não consegui ver "<nome>" na tela.'`

**expect_text**
- Sem valor → `ok=False`, `"Entendi que é uma validação, mas não achei o texto esperado. Coloque a mensagem entre aspas."`
- Depois: `snapshot()`.
- `selector_code`:
  - sem máscara: `expect(page.get_by_text('<texto>')).to_be_visible()`
  - com máscara: `expect(page.get_by_text(re.compile('<regex>'))).to_be_visible()`
- Mensagem: `'A mensagem está na tela: "<texto>"'` ou `'A mensagem NÃO apareceu: "<texto>"'`,
  acrescentando `(comparado com máscara)` quando houver máscara.

Para fill, clear, click e locate, `selector_code = element.selector.to_code()`.

### 3. Mensagens de erro do Playwright

O Playwright devolve um log de chamada enorme. `run_action` captura **qualquer** exceção e
devolve `CommandResult(ok=False, message=erro_curto(exc))`:

```python
def erro_curto(exc: Exception) -> str:
    texto = str(exc)
    primeira = texto.strip().splitlines()[0] if texto.strip() else "erro desconhecido"
    if "intercepts pointer events" in texto:
        return f"{primeira} Tem algo na frente do elemento (um modal aberto?)."
    if "Timeout" in primeira:
        return f"{primeira} O elemento não ficou disponível a tempo."
    return primeira
```

Erros de **conexão com o browser** (tarefa 3) não são erros da ação: deixe subir a exceção
própria (`BrowserUnavailableError`) para a camada de cima responder com o status certo.

### 4. Orquestração mínima para testar de ponta a ponta

**Sem LangGraph nesta sprint.** O fluxo com grafo é a próxima sprint, que vai substituir esta
função:

```python
async def executar_comando(session: AgentSession, texto: str) -> CommandResult:
    interp = await interpret(texto, session)                       # tarefa 5
    if interp.action == Action.EXPECT_TEXT:
        valor = extract_value(texto, "expect_text")                 # tarefa 6
        return await run_expect_text(session, valor)
    if interp.action.needs_element and interp.element is None:
        return CommandResult(ok=False, message=<"Não achei..." com os disponíveis>)
    valor = extract_value(texto, interp.action.value,
                          element_label=interp.element.name if interp.element else "")
    return await run_action(session, interp.action, interp.element, valor)
```

Se a sessão ainda não tem inventário mas a página já está aberta (o outro servidor abriu),
faça um `snapshot()` antes de interpretar.

### 5. Script de teste manual

`scripts/rodar_comandos.py`: recebe uma `cdp_url` e uma lista de comandos (argumentos ou
arquivo), executa um por vez na mesma sessão e imprime, para cada um:

```
[ok] click  Cliquei em "Acessar"
     page.get_by_role('button', name='Acessar', exact=True)
```

O script **para no primeiro erro** e diz quantos comandos ficaram sem executar.

---

## Fora do escopo

- Rota `POST /executar` e persistência no banco (próxima sprint).
- Fluxo em LangGraph e quebra de uma mensagem em vários comandos (próxima sprint).
- `select` e `press` (só existiam no gravador da POC).

---

## Critérios de aceite

- [ ] O **cenário mínimo do BugBank** (seção 7 do contexto) roda inteiro com o
      `scripts/rodar_comandos.py` contra o Chromium "remoto", com os 6 passos `ok`.
- [ ] Cada passo devolve um `selector_code` que, colado em um script Playwright Python
      isolado, executa a mesma ação. Faça um teste que gera o script a partir dos
      `selector_code` e roda.
- [ ] O valor do campo de senha **não** aparece em mensagem nem em log.
- [ ] Clicar em "Registrar" zera o `active_form`, e o próximo `fill` de e-mail vai para o
      formulário de **cadastro**.
- [ ] `expect_text` com máscara: depois de cadastrar uma conta no BugBank,
      `verifique que aparece "A conta XXX-X foi criada com sucesso"` passa.
- [ ] Clique em um elemento coberto por modal devolve `ok=False` com a dica do modal, e não
      um stacktrace.
- [ ] Texto esperado ausente devolve `ok=False` em ~10 s, sem exceção.
- [ ] A conexão caindo no meio da execução gera `BrowserUnavailableError`, e não
      `CommandResult`.
- [ ] Testes unitários do despacho com uma sessão fake (sem browser), cobrindo cada ramo
      de `ok=False`.
- [ ] `PROGRESSO.md` atualizado, com uma seção **"Para a próxima sprint"** listando o que
      falta: rota `/executar`, persistência, LangGraph, quebra de comandos, ajuste de prompt
      por provedor e planejador.
