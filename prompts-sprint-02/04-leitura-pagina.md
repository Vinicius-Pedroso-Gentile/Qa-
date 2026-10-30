# Tarefa 4 — Leitura da página (inventário de elementos)

> Pré-requisito: leia `00-contexto.md` e o `PROGRESSO.md`. As tarefas 1 a 3 já estão prontas.

## Objetivo

Dado um `AgentSession` (tarefa 3), **ler a página viva** e montar a lista de elementos
interativos que a LLM vai poder escolher. Cada elemento só entra na lista se tiver um
**seletor que, testado na página real, aponta para exatamente ele** (Regra 3).

Também faz parte desta tarefa **esperar a página estabilizar** depois de cada ação, porque
ler o DOM no meio de uma transição produz um inventário errado.

Esta é a tarefa mais pesada da sprint e a que mais tem armadilhas. Leia a seção
"Armadilhas reais" antes de escrever código.

---

## O que fazer

### 1. Modelos (`app/agent/models.py`)

Crie `Selector` e `PageElement` exatamente como na seção 6 do contexto, com:

`Selector.to_code()` gerando o código Python do Playwright:

| kind | código gerado |
|---|---|
| `label` | `page.get_by_label('E-mail', exact=True)` |
| `role` | `page.get_by_role('button', name='Acessar', exact=True)`. Com `exact=False`, sem o `exact` |
| `placeholder` | `page.get_by_placeholder('Informe seu e-mail', exact=True)` |
| `text` | `page.get_by_text('Fechar', exact=True)` |
| `css` | `page.locator('#btnCloseModal')` |

- Com `form` preenchido, a base deixa de ser `page` e vira
  `page.locator('form:has(button:text-is("Acessar"))')`.
- Com `nth`, acrescenta `.nth(N)` no fim.
- Use `repr()` dos valores para escapar aspas corretamente.

`PageElement.describe()` gera o texto que a LLM lê, por exemplo
`textbox "Informe seu e-mail" [Acessar]`.

### 2. Coleta no browser (`app/browser/inventory.py`)

Um script JS executado com `page.evaluate(script, stamp_attr)` que:

1. pega os **elementos semânticos**: `input, button, select, textarea, a[href], [role="button"]`;
2. pega também os **"soltos"**: `div, span, p, li, a` com `cursor: pointer`, sem um
   elemento semântico dentro, com texto ≤ 40 caracteres (ou, sem texto, com `id` ou
   `aria-label`), preferindo o **mais interno** quando pai e filho parecem clicáveis;
3. descarta `type="hidden"`, elementos menores que 2×2 px e elementos com
   `visibility:hidden`, `display:none` ou `opacity:0`;
4. descarta o que **não está por cima no próprio centro**
   (`document.elementFromPoint(cx, cy)` não é ele nem descendente dele), mas só quando o
   centro está dentro da viewport;
5. para cada elemento que sobrou: **carimba** um atributo (ex.: `data-agent-id="E7"`) e
   devolve a descrição crua: `id`, `tag`, `role`, `label`, `text`, `dom_id`, `dom_name`,
   `placeholder`, `input_type`, `form` e `editable`.

Regras de descrição:
- **label**: `<label for=id>` → `<label>` ancestral → `aria-label`;
- **role**: o atributo `role` se houver. Senão: `button`/`submit` → `button`; `<a>` com href
  → `link` e sem href → `button`; `select` → `combobox`; `checkbox`, `radio`; `input` e
  `textarea` → `textbox`; qualquer outro clicável → `button`;
- **form**: o texto do botão de submit do `<form>` ancestral. É isso que distingue o
  "e-mail" do login do "e-mail" do cadastro;
- **text**: `innerText` (só a primeira linha, até 60 caracteres). `value` **só** para botões;
- **editable**: vale pelo tipo do elemento, não pelo papel ARIA. `textarea` e `input` que não
  seja botão, checkbox, radio, file, range ou color.

O código de referência completo está no **Anexo A**. Pode adaptar, mas mantenha cada regra:
cada uma existe por causa de um caso real.

### 3. Seletores candidatos

Para cada elemento cru, gere candidatos **do mais semântico para o mais estrutural**:

1. `label` (se houver);
2. `role` + `name=text`, exato;
3. `placeholder`;
4. `css #id` (só sem escopo de formulário);
5. `css [name="..."]`;
6. `text`, exato. É o único que funciona em clicável sem semântica, como o "Fechar" do BugBank;
7. `role` + `name=text`, **não exato**. Botão com ícone de fonte tem o glifo no nome
   acessível (`" Login"`). Vem depois dos exatos porque "Login" também casaria com
   "Login com Google";
8. `css tag:has-text("texto")`, para quando o texto está num filho (o `<i>` do ícone).

### 4. Validação de unicidade

```
para escopo em (sem formulário, com formulário):
    para cada candidato:
        se locator(candidato).count() == 1
           e o atributo de carimbo desse único elemento == id do elemento:
            aceita

se nada passou: para cada candidato sem escopo, tenta .nth(0..9) e aceita o primeiro
                 que aponta para o elemento carimbado (último recurso)

se nada passou: o elemento fica FORA do inventário
```

- Com escopo de formulário, o locator raiz é `page.locator('form:has(button:text-is("<form>"))')`.
- Um candidato que lança exceção é só um candidato a menos, e não um erro.
- Use timeout curto (~1 s) nessas checagens.

### 5. Montar o `PageElement`

- `name`: o primeiro não vazio entre `label`, `text`, `placeholder`, **nome derivado do id**
  e `dom_name`.
- Nome derivado do id: `"btn-TRANSFERENCIA"` → `"TRANSFERENCIA"` (remove o prefixo
  `btn`/`button` e troca `-`/`_` por espaço).

### 6. API da sessão

Acrescente ao `AgentSession` (ou a um serviço que recebe a sessão):

```python
async def snapshot(self) -> list[PageElement]:
    """Relê a página e devolve os elementos com seletor único verificado. Atualiza self.elements."""

def locator(self, element: PageElement) -> Locator:
    """Selector → Locator do Playwright. A única função que traduz seletor em locator:
    o snapshot, a execução e o código gerado usam a mesma tradução."""

async def settle(self) -> None:
    """Espera o DOM parar de mudar."""
```

### 7. Esperar a página estabilizar

**Não use tempo fixo.** No BugBank, a tela troca entre 101 ms e 376 ms depois do mesmo
clique. E amostrar a página de tempos em tempos também falha, porque uma pausa entre dois
renders parece "estável".

O sinal confiável é o próprio navegador: um `MutationObserver` marca a hora da última
mudança no DOM, e a página só é considerada pronta depois de um tempo sem mudanças:

```js
() => {
  if (window.__agentMut === undefined) {
    window.__agentMut = Date.now();
    new MutationObserver(() => { window.__agentMut = Date.now(); })
      .observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  }
  return Date.now() - window.__agentMut;   // ms desde a última mutação
}
```

```
PASSO   = 100 ms    intervalo entre consultas
MINIMO  = 400 ms    nunca decide antes disso
QUIETO  = 500 ms    tempo sem mutação para considerar pronta
LIMITE  = 5000 ms   teto, para página que nunca para (spinner, carrossel)
```

Se o `evaluate` falhar porque a página está navegando, conte como "ainda não está pronta"
e continue. Depois de uma navegação o `window` é novo, o observador se reinstala sozinho e o
contador volta a zero, que é exatamente o comportamento certo.

**Atenção:** o carimbo `data-agent-id` é atributo, e o `MutationObserver` observa atributos.
Garanta que o snapshot não faça o `settle` seguinte esperar à toa. Por exemplo, faça o
snapshot **depois** do settle, e não antes.

---

## Armadilhas reais (todas aconteceram na POC)

| Situação | O que acontecia | Regra que resolve |
|---|---|---|
| Login e cadastro no mesmo DOM, ambos com "Informe seu e-mail" | Seletor ambíguo | Escopo por formulário, pelo texto do botão de submit |
| BugBank vira um cartão 3D entre login e cadastro | A face escondida continua com tamanho e `visibility:visible` | Teste do `elementFromPoint` no centro |
| Modal aberto | Elementos atrás do modal entravam no inventário e o clique falhava | O mesmo teste do `elementFromPoint` |
| "Fechar" do modal é `<a>` sem `href` | Não casava com `a[href]` e o agente não enxergava | Coleta de "soltos" por `cursor:pointer`, incluindo `a` |
| Cards da home são `<a>` vazios, `id="btn-TRANSFERENCIA"` | Elemento sem nome e a LLM não tinha como escolher | Nome derivado do id |
| Depois de preencher a senha | O campo "Informe sua senha" virava "Teste@123" no inventário | `value` só serve de rótulo em botão |
| Busca do Google é `<textarea role="combobox">` | Era tratada como não editável | `editable` pelo tipo do elemento, não pelo role |
| Botão com ícone Font Awesome | Nome acessível `" Login"` não casava exato | Candidato `role` não exato + `:has-text` |
| Seletor casava 2 elementos | O elemento era descartado e o agente "jurava" que não existia | Escopo por formulário, depois `nth` como último recurso |

---

## Fora do escopo

- Escolher o elemento a partir do texto do usuário (tarefa 5).
- Executar ações (tarefa 7).
- Gravador por clique/coordenada da POC.

---

## Critérios de aceite

Testes de integração no BugBank, usando o Chromium "remoto" da tarefa 3:

- [ ] Na tela inicial, o inventário tem os campos de e-mail e senha do **login** e os botões
      "Acessar" e "Registrar", e **não** tem os campos do cadastro (face escondida do cartão).
- [ ] Depois de clicar em "Registrar" (pode clicar direto pelo Playwright no teste), o
      inventário passa a ter os campos do **cadastro**, e os do login saem.
- [ ] Os dois campos "Informe seu e-mail" que aparecem em momentos diferentes têm seletores
      que resolvem para um único elemento. Prove com `locator(...).count() == 1` para cada
      um na hora em que estão visíveis.
- [ ] Com o modal de erro aberto, o inventário tem "Fechar" e **não** tem nada que está
      atrás do modal.
- [ ] Todo `PageElement` devolvido passa no teste: `locator(el).count() == 1`.
- [ ] `Selector.to_code()` gera código que, executado com `eval` em um teste, encontra o
      mesmo elemento que `locator()`. Teste para cada `kind`, com e sem `form` e `nth`.
- [ ] `settle()` volta em menos de 1 s numa página parada e espera a troca de tela do
      BugBank terminar depois do clique em "Registrar".
- [ ] Testes unitários dos candidatos e do nome derivado do id, sem browser.
- [ ] `PROGRESSO.md` atualizado.

---

## Anexo A — Código de referência da POC (JS de coleta)

Copiado de `qai/browser.py`. O carimbo lá se chama `data-qai-id`. Aqui, use um nome do
serviço novo (ex.: `data-agent-id`).

```js
// ---- descrever(el): usado pela coleta ----
const first = (s) => (s || '').split('\n')[0].trim().slice(0, 60);

const descrever = (el) => {
  const type = (el.getAttribute('type') || '').toLowerCase();
  let label = '';
  if (el.id) {
    const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    if (l) label = first(l.innerText);
  }
  if (!label && el.closest('label')) label = first(el.closest('label').innerText);
  if (!label) label = first(el.getAttribute('aria-label'));

  const tag = el.tagName.toLowerCase();
  const isBotao = tag === 'button' || type === 'submit' || type === 'button';
  let role = el.getAttribute('role') || '';
  if (!role) {
    if (isBotao) role = 'button';
    else if (tag === 'a') role = el.getAttribute('href') ? 'link' : 'button';
    else if (tag === 'select') role = 'combobox';
    else if (type === 'checkbox') role = 'checkbox';
    else if (type === 'radio') role = 'radio';
    else if (tag === 'input' || tag === 'textarea') role = 'textbox';
    else role = 'button';  // div/span clicável: age como botão
  }

  // O formulário a que pertence, nomeado pelo texto do seu botão de submit.
  let form = '';
  const f = el.closest('form');
  if (f) {
    const submit = f.querySelector('button[type="submit"]')
      || f.querySelector('input[type="submit"]')
      || f.querySelector('button');
    form = first(submit ? (submit.innerText || submit.value) : '');
  }

  // Dá para digitar aqui? Vale o tipo do elemento, não o papel ARIA.
  const naoEditaveis = ['checkbox', 'radio', 'file', 'range', 'color'];
  const editavel = tag === 'textarea'
    || (tag === 'input' && !isBotao && naoEditaveis.indexOf(type) === -1);

  return {
    editable: editavel,
    tag: tag,
    role: role,
    label: label,
    // el.value só serve de rótulo em botão. Em campo de texto, value é o que foi digitado.
    text: first(el.innerText || (isBotao ? el.value : '') || ''),
    dom_id: el.id || '',
    dom_name: el.getAttribute('name') || '',
    placeholder: el.getAttribute('placeholder') || '',
    input_type: type,
    form: form,
  };
};

// ---- coleta: (stamp) => lista de descrições ----
(stamp) => {
  /* ...descrever acima... */
  const out = [];
  let n = 0;
  const SEMANTICOS = 'input, button, select, textarea, a[href], [role="button"]';

  const soltos = Array.from(document.querySelectorAll('div, span, p, li, a')).filter((el) => {
    if (el.matches(SEMANTICOS)) return false;
    if (getComputedStyle(el).cursor !== 'pointer') return false;
    if (el.querySelector(SEMANTICOS)) return false;
    const texto = (el.innerText || '').trim();
    if (texto.length > 40) return false;
    if (!texto && !el.id && !el.getAttribute('aria-label')) return false;
    // Prefere o elemento mais interno.
    return !Array.from(el.querySelectorAll('*')).some(
      (filho) => getComputedStyle(filho).cursor === 'pointer' && (filho.innerText || '').trim()
    );
  });

  [].concat(Array.from(document.querySelectorAll(SEMANTICOS)), soltos).forEach((el) => {
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden') return;

    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (rect.width < 2 || rect.height < 2) return;
    if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return;

    // Visível de verdade: precisa ser o que está por cima no próprio centro.
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight) {
      const topo = document.elementFromPoint(cx, cy);
      if (topo && topo !== el && !el.contains(topo)) return;
    }

    const descricao = descrever(el);
    const id = 'E' + (++n);
    el.setAttribute(stamp, id);
    descricao.id = id;
    out.push(descricao);
  });

  return out;
}
```
