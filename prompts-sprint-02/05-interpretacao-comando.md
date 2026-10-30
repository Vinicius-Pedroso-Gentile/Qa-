# Tarefa 5 — Interpretação do comando pela LLM

> Pré-requisito: leia `00-contexto.md` e o `PROGRESSO.md`. As tarefas 1 a 4 já estão prontas.
> Esta tarefa usa o `classify()` da tarefa 2 e o inventário (`list[PageElement]`) da tarefa 4.

## Objetivo

Dado **um** comando em linguagem natural e o inventário da página, decidir:
1. **qual ação** é (`goto`, `fill`, `click`, `expect_text`, `locate`, `clear`);
2. **qual elemento** ela usa, escolhido entre os IDs do inventário (ou nenhum).

São **duas chamadas pequenas** de LLM, cada uma com resposta restrita a um enum (Regra 1),
mais **checagens determinísticas** em volta. Elas existem porque o enum obriga o modelo a
sempre devolver *alguma coisa*, mesmo quando a resposta certa é "não existe".

A extração do **valor** (e-mail, senha, URL) **não** é desta tarefa. É da tarefa 6, e nunca
passa pela LLM.

---

## O que fazer

### 1. `Action` (`app/agent/models.py`)

Acrescente o enum `Action` da seção 6 do contexto, com `needs_element`.

### 2. Escolher a ação (`app/agent/interpreter.py`)

```python
async def choose_action(text: str) -> Action
```

Prompt de sistema (ponto de partida vindo da POC; ajuste e meça):

```
Classifique a ação de UM comando de teste web.
goto = abrir uma URL, acessar um site
fill = digitar, informar ou preencher um valor em um campo
click = clicar ou pressionar um botão ou link
expect_text = validar, verificar ou conferir que algo é apresentado na tela;
  só vale quando o comando diz qual texto deve aparecer
locate = apenas localizar ou identificar um campo, sem interagir com ele
clear = apagar ou limpar o conteúdo de um campo
Responda apenas com o JSON.
```

Exemplos few-shot (entrada → saída):

```
COMANDO: Abrir o site https://exemplo.com                     → {"action": "goto"}
COMANDO: Localizar o campo Telefone.                          → {"action": "locate"}
COMANDO: Preencher o campo Nome com Joao                      → {"action": "fill"}
COMANDO: Pressionar o botao Enviar                            → {"action": "click"}
COMANDO: Verificar que a tela exibe Cadastro concluido        → {"action": "expect_text"}
COMANDO: Informe a confirmacao da senha Teste@123             → {"action": "fill"}
COMANDO: Apague o que esta no campo Nome                      → {"action": "clear"}
COMANDO: limpe o campo                                        → {"action": "clear"}
```

O exemplo "confirmação da senha" existe porque a palavra "confirmação" puxa o modelo para
`expect_text`.

- Schema: `enum_schema(action=[a.value for a in CHAT_ACTIONS])`.
- `run_name="escolher_acao"`.
- Se `classify` devolver `{}` ou um valor inválido → `Action.LOCATE`. É a ação mais
  inofensiva: só olha, não mexe.

### 3. Trava determinística sobre `expect_text`

```python
def parece_validacao(text: str) -> bool
```

Se a LLM disse `expect_text` mas o comando **não** tem texto entre aspas, **não** tem `:` e
**não** tem verbo de validação, então a ação vira `fill`.

Verbos de validação (regex, sem diferenciar maiúsculas): `valid\w*`,
`verifi(?:c|qu)\w*`, `confir\w*`, `confer\w*` e `che(?:c|qu)\w*`.

Motivo: `"informe a descrição Pagamento teste"` e `"informe a confirmação da senha"` são
preenchimentos. O modelo confundia por causa do **nome do campo**. Com modelos maiores
isso deve acontecer menos, mas mantenha a trava.

### 4. Escolher o elemento

```python
async def choose_element(text: str, elements: list[PageElement]) -> PageElement | None
```

- Inventário vazio → `None`, **sem** chamar a LLM.
- Prompt de sistema:

```
Escolha qual elemento da página o comando utiliza.

ELEMENTOS DISPONÍVEIS:
E1 = textbox "Informe seu e-mail" [Acessar]
E2 = textbox "Informe sua senha" [Acessar]
E3 = button "Acessar" [Acessar]
...

Responda apenas com o JSON, usando um dos ids acima ou NENHUM.
```

- Schema: `enum_schema(element=[ids...] + ["NENHUM"])`. O enum é **dinâmico** por página.
- `run_name="escolher_elemento"`.
- Depois da resposta:
  1. o ID existe **e** a escolha é **plausível** → devolve o elemento;
  2. caso contrário → **fuzzy** determinístico (abaixo).

### 5. Plausibilidade

```python
def _plausible(text: str, element: PageElement) -> bool:
    return bool(tokens(text) & tokens(element.name))
```

Exige **ao menos uma palavra em comum** entre o comando e o nome do elemento. Na POC, o
pedido "clicar no botão Transferência", numa página sem esse botão, recebeu como resposta
"Cadastrar". O enum obriga o modelo a escolher algo; esta regra transforma o palpite em
"não encontrei", que é a resposta honesta.

### 6. Fuzzy (rede de segurança)

Se a LLM não devolver um ID válido e plausível: pontue cada elemento pelo número de
palavras em comum entre o comando e `"{name} {input_type}"`. Devolva o de maior pontuação
se ela for > 0, ou `None`.

### 7. Desempate entre formulários

```python
def disambiguate(chosen, elements, active_form) -> PageElement | None
```

Quando o elemento escolhido tem um **gêmeo** (mesmo `name` e `role`) em outro formulário:
1. se `active_form` está preenchido, escolha o gêmeo desse formulário;
2. senão, o primeiro da página.

Motivo: no BugBank, "Informe seu e-mail" existe no login e no cadastro. Olhando só o
comando, até uma pessoa ficaria em dúvida.

### 8. Comandos que não nomeiam o campo

- `fill` sem elemento → se a página tem **um único** campo editável, use ele
  (`"digite banana"` no Google).
- `clear` sem elemento → `last_element` da sessão; senão, o único campo editável
  (`"apague isso"`).

### 9. Função que junta tudo

```python
class Interpretation(BaseModel):
    action: Action
    element: PageElement | None

async def interpret(text: str, session: AgentSession) -> Interpretation:
    action = await choose_action(text)
    if action == Action.EXPECT_TEXT and not parece_validacao(text):
        action = Action.FILL
    element = None
    if action.needs_element and session.elements:
        element = await choose_element(text, session.elements)
        element = disambiguate(element, session.elements, session.active_form)
        if element is None and action == Action.FILL:
            element = only_text_field(session.elements)
        if element is None and action == Action.CLEAR:
            element = session.last_element or only_text_field(session.elements)
    return Interpretation(action=action, element=element)
```

Se a ação precisa de elemento e ele ficou `None`, quem chama (tarefa 7) responde algo como
`"Não achei esse elemento na página. Disponíveis: "Acessar", "Registrar", ..."` (até 6 nomes).

### 10. Normalização de texto (`app/agent/textutil.py`)

```python
def normalize(text) -> str   # minúsculas, sem acentos (NFKD), strip
def tokens(text) -> set[str] # palavras alfanuméricas normalizadas com mais de 2 letras
```

Acentos atrapalham qualquer comparação em português: "Transferência" × "transferencia".

---

## Fora do escopo

- Extrair valores (tarefa 6).
- Executar (tarefa 7).
- Quebrar uma mensagem com vários comandos ("preencha X e clique em Y"). É da próxima sprint.
- Ajuste fino de prompt nos três provedores (atividade 10 da estimativa). Aqui basta passar
  nos critérios abaixo com o provedor padrão.

---

## Critérios de aceite

**Unitários (LLM fake, sem rede):**
- [ ] `parece_validacao`: "informe a confirmação da senha Teste@123" → False;
      'verifique "Login ok"' → True; "Mensagem: Sucesso" → True.
- [ ] `_plausible` rejeita "clique em Transferência" → `button "Cadastrar"`.
- [ ] `disambiguate` escolhe o gêmeo do `active_form` e, sem ele, o primeiro.
- [ ] `only_text_field` só devolve algo quando existe exatamente um campo editável.
- [ ] `{}` da LLM → `LOCATE` na ação e fuzzy no elemento.

**Integração (LLM real do provedor padrão + BugBank):**

| Comando | Ação esperada | Elemento esperado |
|---|---|---|
| `abra https://bugbank.netlify.app/` | goto | — |
| `informe o e-mail qualquerCoisa0001@gmail.com` | fill | e-mail do **login** |
| `informe a senha Teste@123` | fill | senha do **login** |
| `clique em Acessar` | click | Acessar |
| `clique em Registrar` | click | Registrar |
| (na tela de cadastro, com `active_form="Cadastrar"`) `informe o e-mail x@y.com` | fill | e-mail do **cadastro** |
| `Informe a confirmação da senha Teste@123` | fill | Confirmação senha |
| `verifique que aparece "Usuário ou senha inválido"` | expect_text | — |
| `clique em Transferência` (na tela de login) | click | **None** |
| `localize o campo de senha` | locate | senha |

- [ ] Todos os casos da tabela passam.
- [ ] Cada comando faz **no máximo 2** chamadas de LLM (conte no teste).
- [ ] `PROGRESSO.md` atualizado, com a taxa de acerto por caso se algum falhar.
