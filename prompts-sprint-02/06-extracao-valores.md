# Tarefa 6 — Extração de valores sem LLM

> Pré-requisito: leia `00-contexto.md` e o `PROGRESSO.md`. Esta tarefa só depende da 1, e
> pode ser feita em paralelo com as tarefas 2 a 5.

## Objetivo

Recortar do texto do comando o **valor literal** que a ação precisa: a URL do `goto`, o
valor do `fill` e o texto esperado do `expect_text`. Tudo com **regex e regras
determinísticas**. O dado de teste **nunca** passa pela LLM (Regra 2).

Também faz parte desta tarefa converter **máscaras** em texto esperado (`"A conta XXXX-X foi
criada"`) em regex, para validar mensagens que têm um trecho variável.

---

## Por que existe

Na POC, quando a LLM foi encarregada de copiar o dado de teste, ela **corrompeu** o valor:
`qualquerCoisa0001@gmail.com` virou `anything0001@gmail.com` (ela traduziu a palavra).
Modelos maiores erram menos, mas o valor vai para um mapeamento que será reexecutado e
nem um erro desses é aceitável.

---

## O que fazer (`app/agent/literals.py`)

### Função principal

```python
def extract_value(text: str, action: str, *, element_label: str = "") -> str | None
```

`element_label` é o nome do elemento já escolhido (tarefa 5). Ele serve para **não**
confundir o nome do campo com o valor ("informe o **nome** Vinicius" → o valor não é "nome").

### `goto`: URL

1. Uma URL com `http(s)://` → ela, sem a pontuação final (`.,;:!?"'”`).
2. Senão, um **domínio sem protocolo** (`bugbank.netlify.app`) → `https://` + domínio. Só
   vale se o texto **não** tiver e-mail, porque `a@b.com` tem cara de domínio.
3. Senão → `None`.

Regex de referência:
```python
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
BARE_DOMAIN_RE = re.compile(r"(?<![@\w.])((?:[\w-]+\.)+[a-z]{2,})(/\S*)?", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
QUOTED_RE = re.compile(r"[\"“”]([^\"“”]{2,})[\"“”]")
```

### `fill`: valor, nesta ordem de prioridade

1. **E-mail** no texto → ele.
2. **Texto entre aspas** (retas ou curvas) que não seja só o nome do campo → ele.
3. **Depois da última vírgula**, se tiver de 2 a 5 palavras e não for cortesia
   (`"coloque no email o seguinte texto, banana pera uva"` → `"banana pera uva"`).
4. **Depois do último verbo-marcador**, descartando do início os artigos e o nome do campo:
   - marcadores: `digite, digitar, escreva, preencha, preencher, informe, informar, insira,
     inserir, coloque, colocar, com, valor, texto`;
   - descartáveis no início: `o, a, os, as, um, uma, de, do, da, no, na, em, campo, valor,
     texto, seguinte, barra`, mais qualquer palavra que **ecoe** o nome do campo;
   - **corte uma locução de lugar no fim**: `no/na/em/dentro do/da` seguido de uma palavra
     que indica o campo (`barra, campo, caixa, busca, pesquisa`) ou que ecoa o nome do campo.
     `"digite banana na barra"` → `"banana"`. **A POC não fazia isso** e devolvia
     `"banana na barra"`. É um bug conhecido, e a regra nova corrige;
   - se sobraram até 3 palavras, o valor é todas elas. Se sobraram mais, é só a primeira
     (era o resto da frase).
5. **Última palavra** do texto.

Cada candidato dos itens 3 a 5 passa pelo filtro `_acceptable`:
- **tem dígito ou símbolo de dado** (`@#$%&*_/+\|~^`) → aceita na hora, mesmo com 1 caractere
  (`"4"`, o dígito da conta, é um valor legítimo). Vírgula e ponto **não** contam como
  símbolo: são pontuação de frase;
- menos de 2 caracteres → rejeita;
- é rótulo e não valor (`campo, senha, email, e-mail, botão, tela, página, modal,
  mensagem, pesquisa, busca`...) → rejeita;
- é cortesia (`por favor, obrigado, ok, beleza, valeu`) → rejeita;
- **ecoa o nome do campo** (igual a uma palavra do label ou com os 4 primeiros caracteres
  em comum, como "pesquisa" para o campo "Pesquisar") → rejeita.

### `expect_text`: texto esperado

1. Texto entre aspas → a **maior** das aspas (é a mensagem esperada).
2. Senão, o que vem depois do primeiro `:`.
3. Senão → `None`. A tarefa 7 responde "coloque a mensagem entre aspas".

### Outras ações → `None`.

### Máscaras em texto esperado

Mensagens de sistema costumam ter um dado que muda a cada execução
(`"A conta 827-9 foi criada com sucesso"`). O usuário escreve a parte variável como
máscara, e ela vira curinga de regex. **O resto continua comparado letra por letra.**

```python
def tem_mascara(texto: str) -> bool
def to_pattern(texto: str) -> re.Pattern | None   # None quando não há máscara
```

- Uma palavra é máscara se, sem a pontuação das pontas, só tem caracteres de `Xx#*.…_-`
  **e** pelo menos **dois** de `Xx#*…`. Assim um hífen solto não vira máscara.
- Cada palavra-máscara vira `\S+`. As outras passam por `re.escape`.
- As palavras são unidas com `\s+`, porque a aplicação pode quebrar a mensagem em linhas.
- `re.IGNORECASE`.

### Normalização

Use `normalize()` e `tokens()` de `app/agent/textutil.py` (criados na tarefa 5. Se a 5
ainda não existir, crie o módulo aqui com a mesma assinatura).

---

## Fora do escopo

- Escolher a ação ou o elemento (tarefa 5).
- Executar a validação na página (tarefa 7).
- Quebrar uma mensagem com vários comandos.

---

## Critérios de aceite

Testes unitários, sem rede nem browser, com **todos** estes casos (todos vieram de bugs ou
de usos reais da POC):

| action | texto | element_label | esperado |
|---|---|---|---|
| goto | `abra https://bugbank.netlify.app/` | | `https://bugbank.netlify.app/` |
| goto | `acesse bugbank.netlify.app.` | | `https://bugbank.netlify.app` |
| goto | `abra o site` | | `None` |
| fill | `informe o e-mail qualquerCoisa0001@gmail.com` | Informe seu e-mail | `qualquerCoisa0001@gmail.com` |
| fill | `informe a senha Teste@123` | Informe sua senha | `Teste@123` |
| fill | `Informe a confirmação da senha Teste@123` | Informe a confirmação da senha | `Teste@123` |
| fill | `informe o nome Vinicius Gentile` | Informe seu Nome | `Vinicius Gentile` |
| fill | `digite banana na barra` | Pesquisar | `banana` (a POC errava este) |
| fill | `digite banana nanica` | Pesquisar | `banana nanica` |
| fill | `coloque no email o seguinte texto, banana pera uva` | Email | `banana pera uva` |
| fill | `preencha o campo Nome com "João da Silva"` | Nome | `João da Silva` |
| fill | `informe o número da conta 4` | Número da conta | `4` |
| fill | `preencha o nome, por favor` | Nome | `None` |
| fill | `digite pesquisa` | Pesquisar | `None` |
| expect_text | `verifique que aparece "Usuário ou senha inválido"` | | `Usuário ou senha inválido` |
| expect_text | `valide a mensagem: Cadastro realizado` | | `Cadastro realizado` |
| expect_text | `verifique a mensagem` | | `None` |
| click | `clique em Acessar` | | `None` |

Máscaras:

| texto | `tem_mascara` | casa com |
|---|---|---|
| `A conta XXXX-X foi criada com sucesso` | True | `A conta 827-9 foi criada com sucesso` |
| `Saldo: R$ ###` | True | `Saldo: R$ 1.250,00` |
| `Login - ok` | False | — |
| `A conta XXXX-X foi criada` | True | **não** casa com `A conta 827-9 foi removida` |

- [ ] Todos os casos das duas tabelas passam.
- [ ] Nenhum import de LLM em `literals.py`.
- [ ] `PROGRESSO.md` atualizado.
