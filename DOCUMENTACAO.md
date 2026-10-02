# Qaí — como funciona, linha por linha

Este documento acompanha **um comando seu**, do momento em que você digita
`python -m qai` até o Playwright terminar de clicar num botão do BugBank. E, no fim
(Parte 13), o que acontece quando esse comando vira um teste salvo que roda sozinho.

Ele é escrito para quem sabe programar mas está começando em IA. Cada trecho de código
aparece com o número da linha real do arquivo, seguido da explicação e — o mais
importante — **do motivo**. Quando o código chama um método de biblioteca, eu explico
o que esse método faz e por que escolhi ele, mas não entro dentro da biblioteca.

> **Como ler:** a ordem dos capítulos é a ordem em que o código realmente executa.
> Se você ler de cima para baixo, está seguindo o caminho de um comando.

---

## Índice

- [Parte 0 — O mapa e o conceito de agente](#parte-0--o-mapa-e-o-conceito-de-agente)
- [Parte 1 — `python -m qai`](#parte-1--python--m-qai)
- [Parte 2 — O servidor sobe](#parte-2--o-servidor-sobe-serverpy)
- [Parte 3 — A página abre no Chrome](#parte-3--a-página-abre-no-chrome-indexhtml)
- [Parte 4 — Você manda a primeira URL](#parte-4--você-manda-a-primeira-url)
- [Parte 5 — O grafo decide o caminho](#parte-5--o-grafo-decide-o-caminho-graphpy)
- [Parte 6 — A LLM decide](#parte-6--a-llm-decide-interpreterpy--llmpy)
- [Parte 7 — O valor literal](#parte-7--o-valor-literal-literalspy)
- [Parte 8 — O browser executa](#parte-8--o-browser-executa-browserpy)
- [Parte 9 — A resposta volta para a tela](#parte-9--a-resposta-volta-para-a-tela)
- [Parte 10 — Vários comandos numa mensagem só](#parte-10--vários-comandos-numa-mensagem-só-commandspy)
- [Parte 11 — A tela ao vivo](#parte-11--a-tela-ao-vivo)
- [Parte 12 — Os arquivos de apoio](#parte-12--os-arquivos-de-apoio)
- [Parte 13 — Gravar e reexecutar um teste](#parte-13--gravar-e-reexecutar-um-teste-suitepy)
- [Glossário](#glossário)

---

# Parte 0 — O mapa e o conceito de agente

## 0.1 O que é um "agente", de verdade

Um **chatbot** recebe texto e devolve texto. Fim.

Um **agente** faz três coisas a mais:

1. **Percebe** um ambiente (aqui: o que está na tela do browser);
2. **Decide** o que fazer (aqui: "isso é um clique, e é no botão Acessar");
3. **Age** sobre esse ambiente através de ferramentas (aqui: o Playwright), e depois
   **percebe de novo** para ver o que mudou.

É esse ciclo *perceber → decidir → agir → perceber* que transforma uma LLM em agente.
No Qaí ele acontece uma vez por comando seu:

```
você digita          →  "clique no botão Acessar"
    PERCEBER         →  lê o DOM da página e monta uma lista de elementos reais
    DECIDIR          →  LLM: que ação é essa? → click
                        LLM: em qual elemento? → E7 ("Acessar")
    AGIR             →  Playwright clica de verdade
    PERCEBER de novo →  relê o DOM (a página mudou! apareceu um modal)
    responder        →  "Cliquei em Acessar"
```

## 0.2 Que tipo de agente é este (e por quê)

Existe um estilo de agente muito na moda em que você entrega tudo para a LLM: "aqui
estão suas ferramentas, aqui está o objetivo, se vira". A LLM decide sozinha quantos
passos dar, em que ordem, quando parar.

**Eu não fiz assim, de propósito.** O motivo é uma medição, não uma opinião.

Antes de escrever a primeira linha deste projeto eu rodei quatro experimentos contra o
seu `qwen3:1.7b`. Dois deles definiram toda a arquitetura:

| Experimento | Resultado |
|---|---|
| Pedir o cenário inteiro de uma vez, resposta livre | ❌ **Degenerou** — repetiu `click` em loop, ignorou o inventário, perdeu os `fill` |
| Pedir **uma** decisão por vez, com lista fechada de respostas | ✅ **5/6 corretos** na ação, **4/4** na escolha do elemento |
| Pedir para a LLM copiar o dado de teste | ❌ **Corrompeu**: `qualquerCoisa0001@gmail.com` virou `anything0001@gmail.com` (ela *traduziu*) |
| Forçar saída em JSON Schema | ✅ JSON sempre válido |

Um modelo de 1.7 bilhões de parâmetros é pequeno. Ele **não** consegue planejar vários
passos nem copiar dados sem errar. Mas ele é bom em uma coisa: **escolher um item de
uma lista curta**. Então o desenho inteiro do Qaí é:

> **A LLM decide. O código determinístico executa.**

O agente aqui tem um **fluxo de controle fixo** (eu que defini, no LangGraph) e a LLM
só preenche duas lacunas dentro dele. Isso é menos "mágico" e muito mais confiável —
e roda na sua máquina, sem API paga.

## 0.3 As três regras

Quase toda decisão estranha que você vai encontrar no código sai de uma destas três:

**Regra 1 — Perguntas pequenas.**
Uma decisão por chamada, com resposta restrita a uma lista fechada. Nunca "o que eu
faço agora?", sempre "isto é `goto`, `fill`, `click`, `expect_text`, `locate` ou
`clear`?".

**Regra 2 — Dado de teste nunca passa pela LLM.**
E-mail, senha, URL, mensagem esperada: tudo é **recortado do seu texto com regex**
(`qai/literals.py`). A LLM nunca vê o valor como algo que ela precisa devolver,
então não tem como corrompê-lo.

**Regra 3 — Seletor nunca é inventado.**
A LLM escolhe um elemento **de uma lista que eu li do DOM vivo**. E antes de entrar
nessa lista, cada seletor é **testado contra a página real** e só é aceito se resolver
para exatamente aquele elemento. Alucinação de seletor é impossível por construção.

## 0.4 As peças

```
qai/
├─ __main__.py     ponto de entrada: valida o Ollama e sobe o servidor
├─ config.py       lê o .env
├─ server.py       FastAPI: as 9 rotas HTTP
├─ web/index.html  o chat + a tela do browser (uma página, sem framework)
├─ commands.py     quebra "faça A e faça B" em dois comandos
├─ graph.py        LangGraph: o fluxo de um comando
├─ interpreter.py  as duas perguntas para a LLM
├─ llm.py          wrapper do ChatOllama
├─ literals.py     extração de valores por regex (sem LLM)
├─ actions.py      o que fazer na página — usado pelo chat e pelo replay
├─ suite.py        grava, salva e reexecuta um teste
├─ browser.py      a sessão Playwright viva + a leitura do DOM
├─ models.py       os tipos de dados
└─ textutil.py     normalização de texto em português

testes/            os testes salvos, um .json por teste
```

E o caminho de uma mensagem entre elas:

```
  navegador (index.html)
        │  POST /api/comando  {"text": "informe a senha Teste@123 e clique em Acessar"}
        ▼
  server.py ──► commands.split_commands()  → 2 comandos
        │
        ├─ comando 1 ──► graph.ainvoke() ─┐
        │                                  │
        │   ┌──────────────────────────────┘
        │   │ interpretar → LLM: ação? LLM: elemento?   (interpreter.py + llm.py)
        │   │ preparar    → regex: qual o valor?        (literals.py)
        │   │ executar    → Playwright age              (actions.py + browser.py)
        │   └─ retorna CommandResult
        │         └─ deu certo? o passo é anotado na gravação  (suite.py)
        │
        └─ comando 2 ──► graph.ainvoke() ── idem
        │
        ▼
  lista de respostas ──► navegador desenha uma bolha por passo
```

E o caminho de um **teste salvo**. Repare no que ele *não* tem:

```
  navegador ──► POST /api/testes/rodar  {"slug": "login-invalido"}
        ▼
  suite.carregar()  → lê testes/login-invalido.json
        ▼
  suite.rodar()     → para cada passo: actions.run_action(...)   (browser.py age)
        ▼
  lista de respostas ──► as mesmas bolhas, no mesmo chat
```

Não há `interpretar`. Não há `preparar`. **Não há chamada ao Ollama.** A decisão que a
LLM tomou uma vez está gravada no arquivo — é a Parte 13.

---

# Parte 1 — `python -m qai`

## 1.1 Por que `python -m qai` e não `python server.py`

Quando você roda `python -m pacote`, o Python procura o arquivo `__main__.py` dentro
dessa pasta e executa ele **com o pacote já importado corretamente**. Isso faz os
imports relativos (`from .config import ...`) funcionarem. Se você rodasse
`python qai/server.py` direto, o Python não saberia que `qai` é um pacote e todo
`from .algo` quebraria.

## 1.2 `qai/__main__.py` — linha por linha

```python
 1  """Sobe o servidor do chat."""
```
Docstring do módulo. Não é decoração: é o que aparece se alguém rodar
`help(qai.__main__)`.

```python
 3  from __future__ import annotations
```
Isto aparece em **todos** os arquivos do projeto, então explico uma vez só.

Ele faz o Python tratar as anotações de tipo (`def f(x: int) -> str`) como **texto**, e
não avaliá-las na hora de importar. Dois ganhos: (a) você pode escrever `int | None` em
versões antigas do Python, e (b) você pode citar um tipo que ainda não foi definido.
Custo zero em tempo de execução.

```python
 5  import sys
 7  from .config import configure_langsmith, settings
 8  from .llm import health_check
```
`sys` para mexer no terminal. Os outros dois são imports relativos — o ponto significa
"deste mesmo pacote".

**Repare no que *não* é importado aqui:** `server`. Isso é proposital, e eu explico na
linha 33.

```python
11  def main() -> int:
```
Retorna `int` porque esse é o **código de saída** do processo. `0` = deu certo,
qualquer outro = deu errado. Scripts e CI conferem isso.

```python
15      try:
16          sys.stdout.reconfigure(encoding="utf-8")
17      except Exception:  # noqa: BLE001 - terminal antigo
18          pass
```
**O que faz:** força o terminal a aceitar UTF-8.

**Por que:** você está no Windows. O console do Windows historicamente usa cp1252, e aí
qualquer `print` com acento ou com um emoji explode em `UnicodeEncodeError` — o
programa morre por causa de um caractere, sem ter feito nada errado.

**Por que o `try`:** `reconfigure` não existe em Python antigo e pode falhar em terminal
exótico. Se falhar, seguimos: não conseguir imprimir bonito não é motivo para não subir
o servidor. O `# noqa: BLE001` silencia o linter, que normalmente reclama de
`except Exception` genérico — aqui é intencional.

```python
20      healthy, message = health_check()
21      if not healthy:
22          print(f"Ollama indisponivel: {message}")
23          return 2
```
**O que faz:** confere que o Ollama está rodando **e** que o modelo do `.env` está
baixado, antes de qualquer outra coisa.

**Por que:** sem isso, o servidor sobe normal, você abre o Chrome, digita a URL, espera,
e só então recebe um erro de conexão dentro do chat — confuso e lento. Falhar aqui, com
a mensagem certa (`Rode: ollama pull qwen3:1.7b`), te economiza dez minutos.

`return 2` — um código de erro diferente de `1` para dizer "o problema é dependência
externa", não "o código quebrou".

```python
25      tracing = configure_langsmith()
26      url = f"http://{settings.host}:{settings.port}"
```
Liga o LangSmith (detalhes em 1.3) e monta a URL que vamos imprimir. Uso as
configurações em vez de fixar `127.0.0.1:8000` para que mudar o `.env` mude também a
mensagem — mensagem que mente é pior que mensagem nenhuma.

```python
28      print("\n  Qaí — agente de teste")
29      print(f"  LLM ......: {settings.ollama_model}")
30      print(f"  LangSmith : {'ativo (' + settings.langsmith_project + ')' if tracing else 'desligado'}")
31      print(f"  Abra no Chrome: {url}\n")
```
O painel de boas-vindas. Cada linha responde a uma pergunta que você faria: *qual modelo
está rodando? o tracing pegou? onde eu clico?*

A linha 30 usa um **operador ternário** dentro da f-string: se `tracing` for verdadeiro
mostra `ativo (Aprendendo)`, senão `desligado`. Isso responde sozinho àquela dúvida de
"será que a chave do LangSmith pegou?".

```python
33      from .server import serve
35      serve()
36      return 0
```
**Import dentro da função.** Esse é o detalhe mais importante do arquivo.

Quando o Python importa `server.py`, ele executa o corpo do módulo — e o corpo do
`server.py` **cria a sessão de browser e compila o grafo** (linhas 30–31 de lá). Se eu
importasse no topo, isso aconteceria *antes* do `health_check`. Resultado: com o Ollama
desligado você pagaria a inicialização inteira só para receber um erro no fim.

Importando aqui, a ordem é: valida ambiente → configura tracing → só então constrói.

`serve()` **bloqueia**: ele entra no laço do servidor e só volta quando você aperta
Ctrl+C. Por isso o `return 0` está depois — ele significa "encerrou de forma limpa".

```python
39  if __name__ == "__main__":
40      raise SystemExit(main())
```
`__name__` só vale `"__main__"` quando o arquivo é **executado**, não quando é
importado. É a proteção padrão do Python.

`raise SystemExit(x)` é a forma idiomática de sair com um código. `SystemExit` é uma
exceção que o interpretador trata de forma especial: ele desmonta tudo direitinho
(fecha arquivos, roda os `finally`) e termina com aquele número.

---

## 1.3 `qai/config.py` — linha por linha

```python
10  ROOT = Path(__file__).resolve().parent.parent
```
`__file__` é o caminho deste arquivo. `.resolve()` transforma em caminho absoluto e
resolve links. O primeiro `.parent` sobe para `qai/`, o segundo para a raiz do
projeto — onde mora o `.env`.

**Por que não usar o diretório atual:** porque o diretório atual é de onde *você
chamou* o comando. Se você rodar o projeto de outra pasta, o `.env` some. Ancorando no
arquivo, ele é sempre achado.

```python
13  class Settings(BaseSettings):
14      model_config = SettingsConfigDict(
15          env_file=ROOT / ".env",
16          env_file_encoding="utf-8",
17          extra="ignore",
18          case_sensitive=False,
19      )
```
**A biblioteca:** `pydantic-settings`. `BaseSettings` é uma classe que lê os campos
declarados a partir de **variáveis de ambiente** e de um arquivo `.env`, já **convertendo
os tipos** e reclamando se algo estiver errado.

**Por que ela e não `os.environ`:** `os.environ["PORT"]` devolve a *string* `"8000"`.
Você teria que converter para `int` na mão, toda vez, e tratar o caso de estar ausente
ou ser lixo. A `BaseSettings` faz isso com a declaração `port: int = 8000` e falha na
hora de subir, com mensagem clara, se alguém escrever `PORT=oito_mil`.

Cada opção:
- `env_file` — onde está o arquivo, usando aquele `ROOT` calculado acima;
- `env_file_encoding="utf-8"` — de novo o Windows: sem isso, um acento no `.env` pode
  virar erro de leitura;
- `extra="ignore"` — se o `.env` tiver uma variável que eu não declarei, ignore em vez
  de explodir. Importante porque o `.env` é seu e pode ter outras coisas;
- `case_sensitive=False` — `OLLAMA_MODEL` no arquivo casa com `ollama_model` na classe.
  Convenção: MAIÚSCULA no ambiente, minúscula no Python.

```python
22      ollama_model: str = "qwen3:1.7b"
23      ollama_base_url: str = "http://localhost:11434"
24      ollama_temperature: float = 0.0
25      ollama_num_ctx: int = 8192
```
Cada linha é *nome do campo : tipo = valor padrão*. Os padrões fazem o projeto rodar
mesmo **sem** `.env` nenhum.

**`temperature = 0.0`** merece parágrafo próprio. Temperatura controla o quanto a LLM
sorteia entre as palavras prováveis. `0.7` é bom para escrever texto criativo. **Zero
faz o modelo sempre escolher a saída mais provável** — o mais perto de determinístico
que dá para chegar. Num agente de teste isso é obrigatório: o mesmo comando tem que
produzir a mesma ação hoje e amanhã, senão você não consegue nem depurar nem confiar.

**`num_ctx = 8192`** é a janela de contexto: quantos tokens o modelo consegue enxergar
de uma vez. O prompt de escolha de elemento carrega o inventário inteiro da página, que
pode ter umas 40 linhas. 8192 dá folga sem gastar RAM à toa.

```python
28      langsmith_tracing: bool = False
29      langsmith_api_key: str = ""
30      langsmith_project: str = "qai-poc"
31      langsmith_endpoint: str = "https://api.smith.langchain.com"
```
Tracing **desligado por padrão**: o projeto tem que rodar para alguém que nem conta no
LangSmith tem.

```python
34      host: str = "127.0.0.1"
35      port: int = 8000
```
`127.0.0.1` e não `0.0.0.0` — de propósito. `127.0.0.1` aceita conexão **só da sua
máquina**. `0.0.0.0` aceitaria de qualquer um na rede, e este servidor dirige um browser
e não tem autenticação nenhuma.

```python
36      # A tela do browser aparece dentro do proprio chat, entao por padrao nao abrimos
37      # uma janela separada. HEADLESS=false volta a mostrar o Chromium de verdade.
38      headless: bool = True
```
**Headless** = o Chromium roda sem janela visível. Como a tela dele é transmitida dentro
do chat (Parte 11), a janela separada só atrapalharia. Se você quiser mostrar o browser
de verdade numa apresentação, `HEADLESS=false` no `.env`.

```python
41  settings = Settings()
```
Uma instância única, criada na importação. Todo mundo faz `from .config import settings`
e lê a mesma coisa. O `.env` é lido uma vez só, aqui.

```python
44  def configure_langsmith() -> bool:
46      if not (settings.langsmith_tracing and settings.langsmith_api_key):
47          os.environ["LANGSMITH_TRACING"] = "false"
48          return False
49      os.environ["LANGSMITH_TRACING"] = "true"
50      os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
51      os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
52      os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
53      return True
```
**O que é o LangSmith:** um painel web onde cada chamada de LLM vira um registro — o
prompt exato que foi enviado, a resposta exata, quanto tempo levou, quantos tokens.
Quando o agente escolhe o elemento errado, você abre o trace e **vê** o que ele viu.
Sem isso, depurar LLM é adivinhação.

**Por que via `os.environ` e não passando parâmetro:** o LangChain lê essas quatro
variáveis sozinho, lá no fundo. Eu não preciso passar nada para o `ChatOllama`; basta
que as variáveis existam **antes** da chamada. Essa é a interface pública do LangSmith.

A linha 46 exige **as duas** coisas: a flag ligada *e* a chave preenchida. Ligar o
tracing sem chave faz o LangChain tentar enviar, falhar e poluir seu terminal de
warnings a cada comando.

A linha 47 escreve `"false"` explicitamente em vez de só não escrever nada. Motivo: se
essa variável já estivesse setada no ambiente do seu terminal, ela venceria o `.env` e o
tracing ligaria sem você pedir. Escrever o valor fecha essa porta.

---

## 1.4 `health_check()` — em `qai/llm.py`

```python
65  def health_check() -> tuple[bool, str]:
67      try:
68          import ollama
70          client = ollama.Client(host=settings.ollama_base_url)
71          available = {m.get("model") or m.get("name") for m in client.list().get("models", [])}
72      except Exception as exc:
73          return False, f"Ollama nao respondeu em {settings.ollama_base_url}: {exc}"
```
`ollama.Client` é o cliente oficial em Python. `client.list()` é o equivalente ao
`ollama list` do terminal: devolve um dicionário com a lista de modelos baixados.

A linha 71 é uma **set comprehension**. O `m.get("model") or m.get("name")` existe
porque a chave mudou de nome entre versões do Ollama — aceitar as duas evita quebrar
quando você atualizar.

O `except` largo é proposital: aqui, *qualquer* falha significa a mesma coisa para você
("o Ollama não está no ar") e a mensagem crua do erro ajuda mais do que atrapalha.

```python
75      if settings.ollama_model not in available:
76          return False, (
77              f"Modelo '{settings.ollama_model}' nao encontrado. "
78              f"Rode: ollama pull {settings.ollama_model}"
79          )
80      return True, f"Ollama OK, modelo {settings.ollama_model}"
```
Erro que **diz o comando exato** para resolver. É a diferença entre uma mensagem que
informa e uma que resolve.

---

# Parte 2 — O servidor sobe (`server.py`)

## 2.1 Por que FastAPI

Você me perguntou isso durante o desenvolvimento, então vale registrar. Três motivos:

1. **`async` nativo.** Este é o motivo decisivo, e explico em 8.1: o Playwright tem duas
   APIs, síncrona e assíncrona, e a síncrona **não pode** ser usada dentro de um
   servidor assíncrono. FastAPI é assíncrono de origem, então o encaixe é natural.
2. **Pydantic embutido.** O mesmo tipo que valida a entrada gera a saída em JSON. Não
   escrevo serialização na mão.
3. **Um arquivo de 225 linhas.** Para uma POC local, Django seria overkill e Flask me
   obrigaria a resolver o `async` na unha.

## 2.2 Linha por linha

```python
27  WEB_DIR = Path(__file__).resolve().parent / "web"
```
Mesma técnica do `ROOT`: caminho ancorado no arquivo, não no diretório atual. O
`/` entre `Path` e string é o operador de junção de caminhos do `pathlib` — funciona
igual no Windows e no Linux, sem você escrever `\` ou `/` na mão.

```python
29  app = FastAPI(title="Qaí")
30  session = BrowserSession()
31  graph = build_graph(session)
32  gravacao = Gravacao()
```
As quatro linhas mais importantes do arquivo. Elas rodam **uma vez**, na importação.

- `app` é a aplicação; os decoradores mais abaixo registram rotas nela.
- `session` é **um** browser, compartilhado por todos os comandos. É isso que faz o
  chat ser uma sessão contínua: você abre o BugBank num comando, preenche no próximo, e
  clica no seguinte — tudo na mesma página, com o estado preservado.
- `graph` é o fluxo compilado, **já amarrado a essa sessão**. Repare que `build_graph`
  recebe a sessão: os nós do grafo são *closures* sobre ela (Parte 5). Compilar uma vez
  e reusar evita refazer esse trabalho a cada mensagem.
- `gravacao` é a lista de passos que deram certo **nesta sessão**, ainda não salvos em
  disco (Parte 13). Ela vive junto da `session` pelo mesmo motivo: gravar um teste é
  anotar o que aconteceu *naquele* browser, naquela sequência.

> ⚠️ **Consequência honesta:** é **um** browser para o servidor inteiro. Dois usuários
> na mesma instância disputariam a mesma página. Para uma POC local isso está certo;
> para multiusuário, `session` precisaria virar um dicionário por sessão.

```python
35  class Command(BaseModel):
36      text: str
```
O corpo que chega no POST. Herdar de `BaseModel` (Pydantic) dá três coisas de graça:
o JSON é convertido em objeto Python, o tipo é validado, e se vier errado o FastAPI
responde 422 com a explicação — sem eu escrever nada.

```python
47  class Reply(BaseModel):
48      ok: bool
49      message: str
50      action: str = ""
51      selector_code: str = ""
52      step: str = ""
53      url: str = ""
54      elements: list[str] = []
```
A resposta. Campo a campo, e por que cada um existe:

| Campo | Para quê |
|---|---|
| `ok` | pinta a borda da bolha de verde ou vermelho |
| `message` | o texto que você lê |
| `action` | rótulo da bolha (`fill`, `click`…) |
| `selector_code` | **o código Playwright equivalente** — o bloco escuro na bolha |
| `step` | `"2/4: clique em Acessar"`, quando a mensagem virou vários passos |
| `url` | a URL atual, mostrada no cabeçalho |
| `elements` | o inventário, para o painel da direita |

O `selector_code` é o que transforma a demo em prova. Sem ele você vê um agente
clicando e tem que acreditar. Com ele você vê **qual seletor** foi usado, e pode copiar
para um teste de verdade.

> Detalhe de Python: `elements: list[str] = []` como padrão mutável seria um bug clássico
> em uma classe comum (todas as instâncias compartilhariam a mesma lista). O Pydantic
> trata isso: ele faz uma cópia nova por instância.

```python
75  def _reply(result: CommandResult) -> Reply:
76      return Reply(
77          ok=result.ok,
78          message=result.message,
79          action=result.action.value if result.action else "",
80          selector_code=result.selector_code,
81          url=session.current_url,
82          elements=[f"{e.describe()}" for e in session.elements],
83      )
```
Converte o resultado interno (`CommandResult`, o que o grafo produz) no formato de saída.

Por que **dois** tipos para a mesma coisa? Porque são coisas diferentes. `CommandResult`
é o vocabulário do agente — tem um `Action` que é enum. `Reply` é o contrato com o
navegador — só tem tipos que viram JSON. Separar deixa eu mudar um sem quebrar o outro.

Linha 79: `.value` converte o enum `Action.CLICK` na string `"click"`. O `if result.action`
protege o caso de erro, em que não houve ação nenhuma.

Linhas 81–82: repare que a URL e os elementos vêm de `session`, **não** de `result`. É
de propósito: eles são o estado *atual* do browser, lido no momento da resposta — depois
que a ação já rodou e a página já foi relida.

```python
86  @app.on_event("startup")
87  def _startup() -> None:
88      configure_langsmith()
```
Roda quando o servidor sobe. É redundante com o `__main__.py`, e é de propósito: se
alguém subir com `uvicorn qai.server:app` direto (sem passar pelo `__main__`), o
tracing ainda liga.

> 🔧 **Dívida técnica conhecida:** `@app.on_event` está **deprecado**. O substituto
> moderno é `lifespan`. Funciona hoje e emite um warning; trocar é uma mudança de umas
> 10 linhas.

```python
91  @app.get("/")
92  def index() -> FileResponse:
93      return FileResponse(WEB_DIR / "index.html")
```
A rota raiz devolve a página do chat. `FileResponse` é a classe do FastAPI que manda um
arquivo do disco, já cuidando do `Content-Type` e do streaming.

**Por que não `StaticFiles`:** é um arquivo só. Montar um diretório estático inteiro
para servir um `index.html` seria mais configuração para o mesmo resultado.

```python
96  @app.get("/api/estado")
97  def estado() -> Reply:
98      return Reply(
99          ok=session.is_open,
100         message="Browser aberto." if session.is_open else "Nenhuma pagina aberta ainda.",
101         url=session.current_url,
102         elements=[e.describe() for e in session.elements],
103     )
```
"Como está tudo agora?". O navegador chama isso **uma vez, ao carregar a página**
(linha 419 do `index.html`).

**Por que existe:** se você der F5 no chat, o JavaScript perde tudo — mas o **servidor
não**. O browser continua aberto, na mesma página. Sem esta rota, o chat recarregado
mostraria "nenhuma página aberta" mentindo para você. Com ela, ele se sincroniza com a
verdade.

É `def` e não `async def`, porque só lê atributos em memória — não espera por nada.

```python
106 @app.post("/api/comando")
107 async def comando(command: Command) -> list[Reply]:
```
**A rota principal.** Três detalhes na assinatura:

- `@app.post` — POST porque isto **muda estado** (o browser vai agir). GET é para ler.
- `command: Command` — a anotação de tipo é o suficiente: o FastAPI vê que é um
  `BaseModel` e entende que aquilo vem do corpo da requisição em JSON.
- `-> list[Reply]` — **lista**, porque uma mensagem sua pode virar vários passos.

```python
113     text = command.text.strip()
114     if not text:
115         return [Reply(ok=False, message="Comando vazio.")]
```
Guarda de entrada. Retorna uma lista de um item para manter o contrato: o JavaScript
sempre itera, nunca precisa checar se veio lista ou objeto.

```python
117     passos = split_commands(text)
118     respostas: list[Reply] = []
120     for indice, passo in enumerate(passos):
```
`split_commands` quebra a mensagem em ordens independentes (Parte 10). `enumerate` dá
índice e valor juntos, para eu poder escrever "2/4".

```python
121         # Antes de executar: um clique que navega ja teria trocado a URL.
122         url_antes = session.current_url
123         try:
124             final = await graph.ainvoke({"text": passo}, config={"run_name": "comando_qai"})
125         except Exception as exc:
126             resposta = Reply(ok=False, message=f"Falhou: {exc}", url=session.current_url)
127         else:
128             resultado = final["result"]
129             resposta = _reply(resultado)
130             # So o que deu certo entra no teste: um passo que falhou nao e um passo.
131             if resultado.ok:
132                 gravacao.registrar(final, url_antes)
```
**A linha 124 é o coração de tudo.**

`graph.ainvoke(...)` roda o grafo do LangGraph do início ao fim. O `a` de `ainvoke` é de
*async* — a versão assíncrona de `invoke`. O `await` significa "pause esta função aqui,
libere o servidor para atender outras coisas, e volte quando terminar".

O primeiro argumento, `{"text": passo}`, é o **estado inicial**. O LangGraph passa um
dicionário de nó em nó, cada um acrescentando suas chaves. No fim, `final` tem tudo que
foi acumulado, e eu pego `final["result"]`.

`config={"run_name": "comando_qai"}` é só um rótulo — é o nome que aparece no
LangSmith. Sem ele, os traces aparecem como `LangGraph` e você não distingue um comando
do outro.

O `except` largo aqui é deliberado: **um erro não pode derrubar o servidor**. Qualquer
exceção vira uma bolha vermelha no chat e a vida continua.

**Por que `else` e não continuar dentro do `try`.** O `else` de um `try` roda só quando
*nada* estourou, e — o ponto — o que acontece dentro dele **não é pego** por aquele
`except`. Isso importa aqui: se a gravação falhasse, o `except` transformaria um comando
que **deu certo** numa bolha vermelha "Falhou:". Separando, o `except` cobre exatamente
o que ele deve cobrir — a execução do grafo.

**Linhas 130–132: é aqui que um teste nasce.** Cada comando bem-sucedido é anotado na
gravação, e note *o que* é anotado: `final` — o estado completo que saiu do grafo, com a
ação escolhida, o elemento já resolvido e o valor já recortado. A interpretação não roda
de novo para gravar; ela já rodou, e o resultado dela estava ali. Detalhe na Parte 13.

**Linha 122, e por que ela vem antes.** `url_antes` é a URL de onde o passo partiu. Lida
depois, ela estaria errada: um clique que navega já teria trocado a página. É o que
permite reexecutar um teste que não começa abrindo a URL.

```python
134         if len(passos) > 1:
135             resposta.step = f"{indice + 1}/{len(passos)}: {passo}"
136         respostas.append(resposta)
```
O rótulo `2/4` só aparece quando **há** mais de um passo. Numa mensagem simples ele
seria ruído.

```python
138         if not resposta.ok:
139             restantes = len(passos) - indice - 1
140             if restantes:
141                 respostas.append(Reply(
142                     ok=False,
143                     message=f"Parei aqui — {restantes} comando(s) seguinte(s) nao foram executados.",
144                     url=session.current_url,
145                 ))
146             break
```
**Para na primeira falha.** Isto é uma decisão de produto, não técnica.

Se o preenchimento da senha falhou, clicar em "Acessar" em seguida só produziria um
*segundo* erro — e aí você teria duas mensagens vermelhas e teria que descobrir qual é a
causa e qual é a consequência. Parando na primeira, a causa fica sozinha na tela.

E a mensagem **diz quantos ficaram para trás**, para você não achar que executou tudo.

> A mesma regra vale na reexecução de um teste salvo, e pela mesma razão (Parte 13).

```python
206 @app.get("/api/tela")
207 async def tela() -> Response:
209     imagem = await session.screenshot()
210     if imagem is None:
211         return Response(status_code=204)
212     return Response(content=imagem, media_type="image/jpeg",
213                     headers={"Cache-Control": "no-store"})
```
Um quadro da tela do browser. Chamado a cada 350ms pelo navegador.

**`204 No Content`** quando não há browser aberto. É o código HTTP certo para "deu tudo
certo, mas não tem corpo nenhum". Melhor que 404 (que significaria "essa rota não
existe") e muito melhor que devolver uma imagem em branco — o JavaScript consegue
distinguir e mostrar o aviso "a tela aparece aqui...".

**`Cache-Control: no-store`** é essencial. Sem ele, o Chrome poderia cachear o primeiro
quadro e reexibi-lo eternamente: o browser agiria e a tela ficaria congelada.
(O JavaScript ainda soma `?t=` + timestamp como segunda trava — cinto e suspensório.)

```python
216 @app.post("/api/encerrar")
217 async def encerrar() -> Reply:
218     await session.close()
219     return Reply(ok=True, message="Browser fechado.")
```
POST porque muda estado. Fecha o Chromium e zera o inventário. O próximo `goto` abre um
browser novo, limpo — útil para recomeçar um cenário sem reiniciar o servidor.

```python
222 def serve() -> None:
223     import uvicorn
225     uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
```
**Uvicorn** é o servidor que realmente fala HTTP. FastAPI define *o que* responder;
uvicorn abre o socket, aceita conexões e roda o laço de eventos assíncrono. A divisão é
padrão em Python: FastAPI é o *framework*, uvicorn é o *servidor ASGI*.

`log_level="warning"` esconde o log de acesso. Com o `/api/tela` sendo chamado 3× por
segundo, o log normal viraria uma cascata que esconderia qualquer mensagem útil.

Import dentro da função de novo — para o `import qai.server` não puxar o uvicorn
quando alguém só quiser inspecionar o módulo.

---

## 2.3 As rotas de gravação e de teste

No arquivo elas ficam entre `/api/comando` e `/api/tela`; agrupei aqui porque as cinco
contam a mesma história. O que cada uma faz está na Parte 13 — aqui interessa o formato.

| Rota | Método | Devolve | Para quê |
|---|---|---|---|
| `/api/gravacao` | GET | `Gravado` | os passos anotados até agora, para o painel |
| `/api/gravacao/limpar` | POST | `Reply` | joga a gravação fora e recomeça |
| `/api/testes` | GET | `list[TesteSalvo]` | os testes que existem em `testes/` |
| `/api/testes` | POST | `Reply` | salva a gravação atual com um nome |
| `/api/testes/rodar` | POST | `list[Reply]` | reexecuta um teste salvo |

```python
39  class Nome(BaseModel):
40      nome: str
43  class Slug(BaseModel):
44      slug: str
57  class PassoGravado(BaseModel):
58      ordem: int
59      label: str
60      selector_code: str
63  class Gravado(BaseModel):
64      url_inicial: str = ""
65      passos: list[PassoGravado] = []
68  class TesteSalvo(BaseModel):
69      slug: str
70      nome: str
71      passos: int
72      criado_em: str
```
Cinco modelos minúsculos em vez de devolver dicionários soltos. O motivo é o mesmo do
`Reply`: **o tipo é o contrato**. O FastAPI gera o JSON a partir dele, e se eu renomear
um campo aqui, o `/docs` muda junto — o navegador e o servidor não saem de sincronia por
descuido.

`Nome` e `Slug` existem porque o FastAPI só lê um corpo JSON se houver um `BaseModel` na
assinatura. Um parâmetro solto `nome: str` viraria *query string*, não corpo.

> **Por que `slug` e não o nome.** O nome do teste é livre: "Login inválido", com espaço
> e acento. O `slug` é a versão higienizada (`login-invalido`) que vira **nome de
> arquivo** e viaja na URL. Manter os dois evita duas classes de problema: nome de
> arquivo inválido no Windows, e ter que escapar acento em todo lugar.

```python
191 @app.post("/api/testes/rodar")
192 async def rodar_teste(alvo: Slug) -> list[Reply]:
194     caso = carregar(alvo.slug)
195     if caso is None:
196         return [Reply(ok=False, message="Nao achei esse teste salvo.")]
198     respostas: list[Reply] = []
199     for rotulo, resultado in await rodar(session, caso):
200         resposta = _reply(resultado)
201         resposta.step = rotulo
202         respostas.append(resposta)
```
A única das cinco que merece o código inteiro, por causa da linha 200.

Ela reusa o **mesmo `_reply`** do chat. O resultado é que a reexecução de um teste chega
no navegador exatamente no formato de um comando digitado: mesma bolha, mesma cor, mesmo
bloco de código embaixo. O JavaScript nem sabe que veio de lugar diferente — e por isso
não precisou de código novo para desenhar (Parte 13.5).

O `rotulo` que vem do `suite.rodar` (`"3/5: clicar: Acessar"`) entra no campo `step`, o
mesmo que o chat usa para "2/4". De novo: um campo, dois usos, zero código extra.

---

# Parte 3 — A página abre no Chrome (`index.html`)

Você abre `http://127.0.0.1:8000`, o FastAPI devolve este arquivo, o Chrome desenha.

É **um arquivo só**, sem React, sem build, sem `npm install`. Motivo: a página tem um
formulário, uma lista e uma imagem que atualiza. Um framework aqui adicionaria uma
etapa de build e centenas de dependências para não resolver nenhum problema que eu
tenha.

## 3.1 O CSS que importa

```css
 8    :root {
 9      --bg: #f4f5f7; --card: #ffffff; --ink: #1c2331; ...
13    @media (prefers-color-scheme: dark) {
14      :root { --bg: #12151a; ... }
```
Variáveis CSS (`--nome`) declaradas em `:root`. O bloco `@media (prefers-color-scheme:
dark)` **redefine** as mesmas variáveis quando o sistema está em modo escuro. Como o
resto do CSS só usa `var(--bg)`, o tema inteiro troca sem nenhuma outra alteração.

```css
21    /* Sem isto, `elemento.hidden = true` nao surte efeito em quem tem display explicito
22       no CSS: a regra do autor ganha da regra [hidden] do navegador, e o aviso continua
23       cobrindo a tela do browser. */
24    [hidden] { display: none !important; }
```
**Isto é a correção de um bug real** que você viu: a tela do browser não aparecia.

O que acontecia: o JavaScript fazia `aviso.hidden = true`, mas eu tinha escrito
`.tela .aviso { display: grid }` no CSS. O atributo `hidden` do HTML funciona porque o
navegador traz uma regra embutida `[hidden] { display: none }` — só que regra **do
autor** (a minha) sempre vence regra **do navegador**. Então `display: grid` ganhava e o
aviso continuava por cima da tela, opaco, para sempre.

Esta linha restabelece a prioridade. É um dos poucos `!important` que eu defendo: ele
não está sobrescrevendo um estilo, está restaurando um comportamento do HTML.

```css
44    main { display: grid; grid-template-columns: 420px 1fr; gap: 14px; ... }
45    @media (max-width: 1000px) { main { grid-template-columns: 1fr; } }
```
Duas colunas: chat com 420px fixos, e o resto (`1fr`) para a tela. Abaixo de 1000px de
largura, vira uma coluna só e as duas áreas empilham.

```css
49    @media (min-width: 1001px) {
50      .direita { max-height: calc(100vh - 116px); overflow-y: auto; }
51    }
```
Com o painel de testes, a coluna da direita passou a ser mais alta que a janela. Em vez
de a **página** rolar (o que levaria o chat junto, para fora da tela), a coluna rola
sozinha — do mesmo jeito que o `#log` do chat já rolava ao lado.

O `min-width: 1001px` casa com o breakpoint de cima: **só** no layout de duas colunas.
Empilhado, limitar a altura esconderia conteúdo, e quem deve rolar é a página.

## 3.2 Os elementos que o JavaScript usa

```html
134   <div id="log"></div>
137   <input id="entrada" ... placeholder="Digite um comando..." autofocus>
144   <img id="tela" alt="tela do browser">
145   <span class="selo" id="selo" hidden>ao vivo</span>
146   <div class="aviso" id="aviso">A tela do browser aparece aqui assim que você mandar uma URL.</div>
151   <ul id="elements"></ul>
152   <p class="empty" id="vazio">Nenhuma página aberta.</p>
```
`#log` recebe as bolhas. `#entrada` tem `autofocus` para você já sair digitando. `#tela`
recebe cada quadro. `#aviso` começa visível e some no primeiro quadro; `#selo` faz o
inverso.

E o painel de testes, que é o terceiro `<aside>` da coluna da direita:

```html
157   <ol id="gravacao"></ol>
158   <p class="empty" id="semGravacao">
162   <input id="nomeTeste" autocomplete="off" placeholder="nome do teste">
163   <button class="ghost" id="salvarTeste">Salvar</button>
164   <button class="ghost" id="descartar" title="Esquecer os passos gravados até agora">Descartar</button>
168   <ul id="testes"></ul>
169   <p class="empty" id="semTestes">Nenhum teste salvo ainda.</p>
```
`#gravacao` é `<ol>` e não `<ul>` porque **ordem é a informação**: um teste é uma
sequência, e o passo 3 depois do 2 não é detalhe visual. `#semGravacao` e `#semTestes`
seguem o padrão do `#vazio` — um texto explicativo que some quando há conteúdo.

## 3.3 `bolha()` — desenhar uma mensagem

```javascript
193 function bolha(texto, quem, estado, codigo, rotulo) {
194   const div = document.createElement('div');
195   div.className = 'msg ' + quem + (estado ? ' ' + estado : '');
```
`quem` é `'user'` ou `'bot'` (decide o lado e a cor); `estado` é `'ok'` ou `'fail'`
(decide a barrinha lateral verde/vermelha).

```javascript
196   if (rotulo) {
197     const tag = document.createElement('span');
199     tag.textContent = rotulo;
200     div.appendChild(tag);
202   div.appendChild(document.createTextNode(texto));
203   if (codigo) {
204     const pre = document.createElement('code');
205     pre.textContent = codigo;
```
**Repare: `textContent` e `createTextNode`, nunca `innerHTML`.**

Isso é segurança, e aqui não é paranoia teórica. O `message` que chega do servidor pode
conter **texto vindo da página que você está testando** (nomes de elementos, mensagens
de erro do site). Se eu usasse `innerHTML`, um site com `<img onerror=...>` no texto de
um botão executaria script dentro do seu chat. `textContent` trata tudo como texto
literal e fecha essa porta.

```javascript
208   log.appendChild(div);
209   log.scrollTop = log.scrollHeight;
210   return div;
```
Rola para o fim (`scrollHeight` é a altura total do conteúdo). E **retorna o elemento** —
é isso que permite criar a bolha "..." e removê-la depois (linha 242/252).

## 3.4 `atualizar()` e `montarChips()`

```javascript
213 function atualizar(dados) {
214   urlEl.textContent = dados.url || '';
215   lista.innerHTML = '';
216   const itens = dados.elements || [];
217   vazio.hidden = itens.length > 0;
```
Sincroniza o cabeçalho e o painel da direita. `lista.innerHTML = ''` limpa (aqui é
seguro: string vazia não tem o que injetar). O `|| ''` e `|| []` protegem contra campos
ausentes.

Linha 217 é um truque compacto: `vazio.hidden` recebe `true` exatamente quando há itens
— ou seja, "Nenhuma página aberta" some quando há elementos.

```javascript
225 function montarChips() {
230     b.textContent = exemplo.length > 38 ? exemplo.slice(0, 36) + '…' : exemplo;
231     if (exemplo.length > 120) b.textContent = '▶ cenário inteiro de uma vez';
232     b.title = exemplo;
233     b.onclick = () => { entrada.value = exemplo; entrada.focus(); };
```
Os botõezinhos de exemplo. Texto longo é truncado; o cenário inteiro ganha um rótulo
especial. `b.title` põe o texto completo no tooltip. O clique **preenche o campo mas não
envia** — de propósito, para você poder editar antes.

---

# Parte 4 — Você manda a primeira URL

Você digita `https://bugbank.netlify.app/` e aperta Enter.

## 4.1 O envio, no navegador

```javascript
274 form.onsubmit = (e) => {
275   e.preventDefault();
276   const texto = entrada.value.trim();
277   if (texto) enviarComando(texto);
278 };
```
`e.preventDefault()` cancela o comportamento nativo do formulário, que seria recarregar
a página inteira. Sem ele, o chat sumiria a cada Enter.

```javascript
238 async function enviarComando(texto) {
239   bolha(texto, 'user');
240   entrada.value = '';
241   enviar.disabled = true;
242   const pensando = bolha('...', 'bot');
```
Ordem pensada: a sua bolha aparece **na hora**, o campo limpa, o botão desabilita (para
você não disparar dois comandos concorrentes no mesmo browser) e um "..." indica que
algo está acontecendo.

Isso importa porque o comando **demora**: são duas chamadas de LLM local mais o
Playwright. Uma tela parada por três segundos parece travada.

```javascript
245     const resposta = await fetch('/api/comando', {
246       method: 'POST',
247       headers: { 'Content-Type': 'application/json' },
248       body: JSON.stringify({ text: texto }),
249     });
```
`fetch` é a função nativa do navegador para HTTP. O header `Content-Type` é o que faz o
FastAPI interpretar o corpo como JSON e preencher aquele `Command`.

```javascript
251     const passos = await resposta.json();
252     pensando.remove();
253     mostrarPassos(passos);
```
Recebe a **lista**, remove o "...", e entrega para quem desenha:

```javascript
266 function mostrarPassos(passos) {
267   for (const passo of passos) {
268     const rotulo = passo.step || passo.action;
269     bolha(passo.message, 'bot', passo.ok ? 'ok' : 'fail', passo.selector_code, rotulo);
270   }
271   if (passos.length) atualizar(passos[passos.length - 1]);
272 }
```
Uma bolha por passo. Linha 271: só o **último** passo atualiza o painel lateral. Motivo:
cada resposta carrega o estado do browser no momento em que foi gerada; o estado final é
o do último. Aplicar todos faria a lista piscar entre telas antigas.

**Por que isso virou função separada.** Rodar um teste salvo devolve exatamente o mesmo
formato (Parte 2.3), então ele desenha com esta mesma função. Enquanto estava inline
dentro do `enviarComando`, o replay teria que duplicar o laço — e duas cópias divergem.

```javascript
257   } finally {
258     enviar.disabled = false;
259     entrada.focus();
260     atualizarGravacao();
261   }
```
`finally` roda **sempre**, tenha dado certo ou errado. Se o botão só fosse reabilitado no
caminho de sucesso, um erro deixaria o chat travado para sempre.

Linha 260: depois de cada comando o painel de gravação é relido do servidor. Ele fica no
`finally` porque o passo pode ter dado certo mesmo numa mensagem que terminou em erro —
"preencha X e clique em Y" com o clique falhando ainda gravou o preenchimento.

## 4.2 `split_commands` vê que só há um comando

Detalhado na Parte 10. Para uma URL sozinha, ele devolve `["https://bugbank.netlify.app/"]`.

---

# Parte 5 — O grafo decide o caminho (`graph.py`)

## 5.1 O que é o LangGraph e por que usar

**LangGraph** é uma biblioteca para descrever um fluxo como uma **máquina de estados**:
você declara nós (funções) e arestas (o que vem depois de quê), e ele executa passando
um estado de um nó para o outro.

Por que não simplesmente um `if/else` numa função? Três razões concretas:

1. **O fluxo fica declarado, não espalhado.** As linhas 195–217 são um desenho do
   comportamento inteiro. Você lê o fluxo sem ler a lógica.
2. **Cada nó aparece separado no LangSmith.** Quando um comando erra, o trace mostra
   *em que nó* e com que estado. Depurar vira leitura, não adivinhação.
3. **Dá para crescer.** Um nó de "tentar de novo com outro seletor" ou de "diagnosticar
   a falha" entra como nó e aresta, sem reescrever o resto.

> É importante ser honesto sobre o que o LangGraph **não** está fazendo aqui: ele não
> deixa a LLM escolher o próximo passo. O roteamento é 100% determinístico, escrito por
> mim. O LangGraph está sendo usado como estrutura e como instrumentação, não como
> autonomia.

## 5.2 O estado

```python
34  class CommandState(TypedDict, total=False):
35      text: str
36      action: Action
37      element: Optional[PageElement]
38      value: Optional[str]
39      result: CommandResult
```
O dicionário que viaja pelo grafo. `TypedDict` é um dicionário comum em execução, mas com
os tipos declarados para o editor e para o LangGraph.

`total=False` significa **todas as chaves são opcionais**. É necessário: no começo só
existe `text`; `action` e `element` aparecem depois do primeiro nó; `result` só no fim.

Cada nó retorna um dicionário **parcial**, e o LangGraph mescla com o estado. O nó
`interpretar` devolve `{"action": ..., "element": ...}` e não precisa repassar o `text`.

## 5.3 `build_graph(session)` e o porquê das closures

```python
42  def build_graph(session: BrowserSession):
43      async def interpretar(state: CommandState) -> dict:
```
Os nós são funções **definidas dentro** de `build_graph`. Isso as torna *closures*: elas
enxergam a variável `session` do escopo de fora, para sempre.

**Por que assim:** o estado do LangGraph é serializável — um dicionário de dados. Um
objeto de browser vivo, com sockets e processo filho, não cabe ali. As alternativas
seriam uma variável global (bagunçado) ou passar a sessão em toda chamada (repetitivo).
A closure resolve: o grafo nasce amarrado a uma sessão e os nós só falam de dados.

## 5.4 Nó `interpretar` — a única parte com IA

```python
44          action = await choose_action(state["text"])
```
**Primeira chamada de LLM.** "Que ação é esta?" Detalhe na Parte 6.

```python
45          if action == Action.EXPECT_TEXT and not parece_validacao(state["text"]):
46              action = Action.FILL
```
**Uma trava determinística por cima da LLM.** Isto corrige um erro real e recorrente.

O modelo via `"informe a descrição Pagamento teste"` ou `"informe a confirmação da senha
Teste@123"` e classificava como **validação** — porque as palavras *descrição* e
*confirmação* têm cara de verbo de conferência. Mas o comando é um **preenchimento**; o
que confundiu o modelo foi o **nome do campo**.

A regra: `expect_text` só faz sentido se o comando disser **qual texto** deve aparecer.
Se não há texto esperado nem verbo de validação, o modelo se enganou — e a gente
corrige. Ensinar isso por exemplo (few-shot) ajudou, mas não foi suficiente; a trava
determinística fecha a conta.

```python
47          element = None
48          if action.needs_element and session.elements:
```
`needs_element` é uma propriedade do enum (Parte 12): vale `True` para `fill`, `click`,
`locate` e `clear`. `goto` e `expect_text` agem na página inteira.

A segunda condição evita uma chamada de LLM inútil: sem página aberta, não há o que
escolher.

```python
49              element = await choose_element(state["text"], session.elements)
50              element = disambiguate(element, session.elements, session.active_form)
```
**Segunda chamada de LLM**, e logo em seguida o desempate determinístico — quando o
mesmo campo existe em dois formulários (o "Informe seu e-mail" do login e o do
cadastro, no BugBank). Parte 6.

```python
51              if element is None and action == Action.FILL:
52                  element = only_text_field(session.elements)
```
Rede de segurança: `"digite banana"` não nomeia campo nenhum. Se a página tem **um** só
campo de texto (Google), não há ambiguidade — use ele.

```python
53              if element is None and action == Action.CLEAR:
54                  # "apague isso" nao nomeia campo nenhum: vale o ultimo em que mexemos.
55                  element = session.last_element or only_text_field(session.elements)
```
`session.last_element` é **a única memória de conversa que existe** neste agente. Ela
permite "apague isso" se referir ao campo que acabou de ser preenchido.

> Decisão consciente: não implementei histórico de conversa completo. Com um modelo de
> 1.7B, carregar as mensagens anteriores no prompt aumenta muito a chance de ele se
> confundir, e resolveria um caso que raramente aparece. Um único ponteiro para o último
> elemento cobre o uso real com custo zero.

```python
56          return {"action": action, "element": element}
```

## 5.5 Nó `preparar` — o valor, sem IA

```python
58      async def preparar(state: CommandState) -> dict:
59          element = state.get("element")
60          value = extract_value(
61              state["text"],
62              state["action"].value,
63              element_label=element.name if element else "",
64          )
65          return {"value": value}
```
Aqui a **Regra 2** vira código: o valor é recortado do seu texto por regex, sem LLM.

Repare no `element_label`: a extração precisa saber o **nome do campo** para não
confundir rótulo com valor. Em `"informe o nome Vinicius Gentile"`, sem saber que o
campo se chama "Nome", o extrator devolveria `"nome Vinicius Gentile"`. Parte 7.

## 5.6 Nó `executar` — e o despacho em `actions.py`

```python
67      async def executar(state: CommandState) -> dict:
68          return {"result": await run_action(
69              session, state["action"], state.get("element"), state.get("value"),
70          )}
```
O nó virou um adaptador de três linhas: tira do estado o que interessa e chama
`run_action`. **O trabalho de verdade mora em `actions.py`**, fora do grafo.

**Por que fora.** Existem dois caminhos até um clique neste projeto: você digitando
"clique em Acessar" no chat, e um teste salvo reexecutando o passo 4 (Parte 13). Se cada
caminho tivesse o seu próprio código de clicar, os dois divergiriam com o tempo — e aí o
teste gravado deixaria de provar o que promete, porque não seria mais a mesma ação. Com
uma implementação só, o replay repete **o clique exato** que foi gravado.

O grafo decide *o que* fazer; o `actions.py` faz. É a mesma separação que já existe entre
decidir (LLM) e executar (código determinístico), um nível abaixo.

```python
31  async def run_action(
32      session: BrowserSession,
33      action: Action,
34      element: Optional[PageElement],
35      value: Optional[str],
36  ) -> CommandResult:
37      try:
38          return await _despachar(session, action, element, value)
39      except Exception as exc:
40          return CommandResult(ok=False, message=erro_curto(exc))
```
Uma casca fina de proteção em volta do trabalho real. **Nenhuma falha do Playwright pode
derrubar o servidor**; toda falha vira uma bolha vermelha.

Repare na assinatura: `session, action, element, value` — quatro parâmetros soltos, não o
`CommandState`. É o que deixa um teste salvo chamar a mesma função sem precisar inventar
um estado de grafo falso só para atravessá-la.

```python
20  def erro_curto(exc: Exception) -> str:
22      texto = str(exc)
23      primeira = texto.strip().splitlines()[0] if texto.strip() else "erro desconhecido"
24      if "intercepts pointer events" in texto:
25          return f"{primeira} Tem algo na frente do elemento (um modal aberto?)."
26      if "Timeout" in primeira:
27          return f"{primeira} O elemento nao ficou disponivel a tempo."
28      return primeira
```
**Tradutor de erro.** O Playwright, quando falha, despeja um *call log* de 30+ linhas com
cada tentativa de retry. Isso é ótimo no terminal e horrível numa bolha de chat.

Pego a primeira linha e, para os dois erros mais comuns, acrescento **a causa provável em
português**. `"intercepts pointer events"` é literalmente "tem um modal aberto na
frente" — foi exatamente o que aconteceu nos seus testes com o botão EXTRATO.

### O despacho, ação por ação

```python
49      if action == Action.GOTO:
50          if not value:
51              return CommandResult(ok=False, message="Nao reconheci uma URL nesse comando.")
52          await session.goto(value)
53          found = await session.snapshot()
54          session.active_form = ""
55          return CommandResult(
56              ok=True,
57              action=action,
58              value=value,
59              message=f"Abri {value} — mapeei {len(found)} elementos na pagina.",
60          )
```
O padrão que se repete: **agir → reler a página → responder**.

`snapshot()` é o "perceber" do ciclo do agente. Sem ele, o próximo comando escolheria
elementos da página **anterior**.

Linha 54: página nova, contexto zerado. A mensagem diz **quantos elementos** foram
mapeados — é o seu sinal de que o agente realmente enxergou a página.

```python
62      if element is None:
63          return CommandResult(ok=False, message="Preciso abrir uma pagina antes.")
```
Guarda defensiva. Vindo do chat, o roteador (`rota`, linha 82 do `graph.py`) já desvia
esse caso para o nó `faltou_elemento` antes de chegar aqui. Mas `_despachar` agora também
é chamado pelo replay, que **não passa pelo roteador** — a guarda deixou de ser teórica.

```python
65      if action == Action.FILL:
66          if not value:
67              return CommandResult(
68                  ok=False,
69                  message=f'Entendi que e para preencher "{element.name}", mas nao achei o valor no comando.',
70              )
```
**Mensagem de erro que ensina.** Ela diz o que o agente entendeu (*o campo*) e o que
faltou (*o valor*). Você olha e já sabe reescrever o comando. Comparado a um "não
entendi", é a diferença entre ficar preso e seguir.

```python
71          await session.fill(element, value)
72          await session.snapshot()
73          session.active_form = element.form
74          session.last_element = element
```
Preenche, relê, e **anota em qual formulário você está**. Esse `active_form` é o que faz
o próximo `"informe a senha"` ir para o formulário certo quando existem dois na tela.

```python
91      if action == Action.CLICK:
92          await session.click(element)
93          await session.snapshot()
94          # So um botao de submit confirma em que formulario estamos. "Registrar" mora
95          # dentro do formulario de login, mas clicar nele leva para o de cadastro --
96          # manter "Acessar" como ativo faria os campos seguintes irem para a tela errada.
97          ehSubmit = normalize(element.name) == normalize(element.form)
98          session.active_form = element.form if ehSubmit else ""
```
**Outro bug real, corrigido.** Um clique nem sempre confirma o formulário.

Lembre do `form` de um elemento: é o **texto do botão de submit** do formulário em que
ele mora. O botão "Registrar" do BugBank fica *dentro* do formulário de login, então
`element.form == "Acessar"`. Se eu marcasse `active_form = "Acessar"` ao clicar nele, os
próximos campos iriam para o formulário de login — mas o clique acabou de te levar para
o de **cadastro**.

A linha 97 testa: *o nome do elemento é igual ao nome do formulário?* Se sim, é o
próprio botão de submit, e o formulário está confirmado. Se não, é um botão de
navegação: zeramos o contexto e deixamos o próximo comando decidir do zero.

`normalize()` compara sem acento e sem maiúscula (Parte 12).

```python
106     if action == Action.LOCATE:
107         visivel = await session.is_visible(element)
108         session.active_form = element.form if visivel else session.active_form
```
`locate` é a ação "não faça nada, só me diga se está aí". Ela existe porque cenários de
teste têm passos assim ("Localizar o campo E-mail") e sem essa ação a LLM seria forçada
a classificá-los como outra coisa.

Interessante: mesmo sem agir, um `locate` bem-sucedido **estabelece o contexto do
formulário**. "Localizar o campo E-mail do cadastro" prepara o terreno para os `fill`
seguintes.

## 5.7 Nó `validar_texto` — e `run_expect_text`

Mesma divisão do nó anterior: o nó adapta, o `actions.py` faz.

```python
72      async def validar_texto(state: CommandState) -> dict:
73          return {"result": await run_expect_text(session, state.get("value"))}
```

```python
119 async def run_expect_text(session: BrowserSession, value: Optional[str]) -> CommandResult:
120     if not value:
121         return CommandResult(
122             ok=False,
123             message="Entendi que e uma validacao, mas nao achei o texto esperado. "
124                     "Coloque a mensagem entre aspas.",
125         )
```
De novo: erro que **diz o que fazer** ("coloque entre aspas").

Por que esta não entrou no `_despachar` junto das outras: validar texto **não tem
elemento**. Ela age na página inteira, com uma assinatura diferente (só o texto
esperado). Enfiá-la no mesmo despacho obrigaria a fingir um elemento nulo no caminho
inteiro. Duas portas, cada uma com a forma do que passa por ela.

```python
126     encontrado = await session.has_text(value)
127     await session.snapshot()
```
`has_text` procura o texto na tela (Parte 8.6). E note: mesmo uma *validação* relê a
página — validar às vezes acontece depois de um modal aparecer, e o próximo comando vai
precisar dos elementos desse modal (o botão "Fechar", por exemplo).

```python
129     padrao = to_pattern(value)
130     if padrao is None:
131         codigo = f"expect(page.get_by_text({value!r})).to_be_visible()"
132         nota = ""
133     else:
134         codigo = f"expect(page.get_by_text(re.compile({padrao.pattern!r}))).to_be_visible()"
135         nota = " (comparado com máscara)"
```
Monta o código Playwright equivalente, para você ver e copiar. É também **o que fica
gravado** no passo quando a validação entra num teste salvo (Parte 13), já que aqui não
há elemento de onde tirar um seletor depois.

`{value!r}` usa `repr()` em vez de `str()`: isso coloca as aspas e escapa o que precisar,
produzindo um literal Python **válido** e colável. Detalhe pequeno, diferença grande
entre um código decorativo e um código utilizável.

O `nota` avisa **na mensagem** quando a comparação foi por máscara. Uma validação que
passou com curinga não é a mesma coisa que uma que passou letra por letra, e você tem
que conseguir distinguir.

```python
142     message=(f'A mensagem esta na tela{nota}: "{value}"' if encontrado
143              else f'A mensagem NAO apareceu{nota}: "{value}"'),
```
Repare em `ok=encontrado`: se o texto não apareceu, a resposta é **vermelha**. Uma
validação que falha *é* um resultado de teste válido — talvez o bug que você está
caçando. Ela não é um erro do agente.

## 5.8 Nó `faltou_elemento`

```python
75      async def faltou_elemento(state: CommandState) -> dict:
76          disponiveis = ", ".join(f'"{e.name}"' for e in session.elements[:6]) or "nenhum"
77          return {"result": CommandResult(
78              ok=False,
79              message=f"Nao achei esse elemento na pagina. Disponiveis: {disponiveis}.",
80          )}
```
**Dizer "não achei" é uma funcionalidade**, não uma falha.

O problema que isto resolve: como a LLM é forçada a escolher da lista, ela **sempre**
escolhe alguma coisa. Pedimos "clicar em Transferência" numa página sem esse botão e ela
respondeu "Cadastrar" — e o agente clicou. Isso é muito pior que não fazer nada.

O `_plausible()` (Parte 6.5) detecta esse palpite e devolve `None`, e este nó transforma
o `None` numa resposta honesta — **que ainda lista o que existe**, para você corrigir o
comando. `[:6]` limita para a bolha não virar um paredão.

## 5.9 O roteamento

```python
82      def rota(state: CommandState) -> str:
83          action = state["action"]
84          if action == Action.EXPECT_TEXT:
85              return "validar"
86          if action.needs_element and state.get("element") is None:
87              return "faltou"
88          return "seguir"
```
Uma função comum que olha o estado e devolve **uma string**. Essa string é a chave do
mapa de destinos.

```python
90      builder = StateGraph(CommandState)
91      builder.add_node("interpretar", interpretar)
...
95      builder.add_node("faltou_elemento", faltou_elemento)
97      builder.set_entry_point("interpretar")
```
`StateGraph(CommandState)` cria o construtor dizendo qual é o formato do estado.
`add_node(nome, funcao)` registra cada nó. `set_entry_point` diz por onde começa.

```python
98      builder.add_conditional_edges(
99          "interpretar",
100         rota,
101         {"seguir": "preparar", "validar": "preparar", "faltou": "faltou_elemento"},
102     )
```
"Depois de `interpretar`, chame `rota`; o que ela devolver, procure neste mapa."

Repare que `"seguir"` e `"validar"` vão **para o mesmo lugar**. Nesta primeira bifurcação
o que realmente se decide é: *dá para continuar, ou faltou o elemento?* Tanto executar
quanto validar precisam do valor extraído, então os dois passam por `preparar`.

```python
103     builder.add_conditional_edges(
104         "preparar",
105         lambda s: "validar" if s["action"] == Action.EXPECT_TEXT else "executar",
106         {"validar": "validar_texto", "executar": "executar"},
107     )
```
**Agora** os caminhos se separam — depois que os dois já pegaram o valor. Aqui a função
de roteamento é simples o bastante para caber num `lambda`.

```python
108     builder.add_edge("executar", END)
109     builder.add_edge("validar_texto", END)
110     builder.add_edge("faltou_elemento", END)
112     return builder.compile()
```
`END` é a constante do LangGraph que marca o fim. Os três caminhos terminam.

`compile()` valida o grafo (todo nó alcançável? toda aresta aponta para algo que
existe?) e devolve o objeto executável com `.ainvoke()`. Roda **uma vez**, na
importação do `server.py`.

---

# Parte 6 — A LLM decide (`interpreter.py` + `llm.py`)

Esta é a única parte do projeto com inteligência artificial de verdade. São **duas
perguntas**, e nada mais.

## 6.1 O wrapper: `llm.py`

```python
19  _THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
```
O qwen3 é um modelo "de raciocínio": ele escreve o pensamento dele dentro de tags
`<think>...</think>` antes da resposta. Eu desligo isso (linha 45), mas guardo esta
regex como rede de segurança — se escapar um bloco, ele é removido antes do parse.

`re.DOTALL` faz o `.` casar também com quebra de linha; sem isso, um bloco de
pensamento com várias linhas não seria removido. O `.*?` é **preguiçoso**: para no
primeiro `</think>`, não no último.

```python
22  def enum_schema(**props: Iterable[str]) -> dict[str, Any]:
24      return {
25          "type": "object",
26          "properties": {k: {"type": "string", "enum": list(v)} for k, v in props.items()},
27          "required": list(props),
28      }
```
**Esta função pequena é o que segura o projeto de pé.** Ela monta um **JSON Schema**.

Chamar `enum_schema(action=["goto", "fill", "click"])` produz:

```json
{
  "type": "object",
  "properties": {"action": {"type": "string", "enum": ["goto", "fill", "click"]}},
  "required": ["action"]
}
```

E o Ollama usa isso para **decodificação restrita** (*constrained decoding*). Vale
entender o mecanismo, porque é o que torna um modelo de 1.7B utilizável:

> A cada token que a LLM vai gerar, ela produz uma probabilidade para **cada** palavra
> possível do vocabulário. A decodificação restrita **zera** a probabilidade de qualquer
> token que levaria a uma saída fora do schema. O modelo não é *pedido* para responder
> em JSON com um dos valores — ele fica **incapaz** de responder outra coisa.

Consequência prática: `json.loads` nunca falha por formato, e `Action(result["action"])`
nunca recebe um valor inventado. Aquele *"sempre JSON válido"* da minha tabela de
experimentos vem daqui.

`**props` aceita qualquer nome de campo; eu uso `action=` e `element=`.

```python
31  async def classify(
32      *,
33      system: str,
34      examples: list[tuple[str, str]],
35      user: str,
36      schema: dict[str, Any],
37      run_name: str,
38  ) -> dict[str, Any]:
```
O `*` sozinho força **todos** os argumentos a serem nomeados. Com seis parâmetros, quase
todos string, chamar posicionalmente seria um convite a trocar dois de lugar e não
perceber.

```python
40      llm = ChatOllama(
41          model=settings.ollama_model,
42          base_url=settings.ollama_base_url,
43          temperature=settings.ollama_temperature,
44          num_ctx=settings.ollama_num_ctx,
45          reasoning=False,  # desliga o <think> do qwen3
46          format=schema,
47          num_predict=128,
48      )
```
**`ChatOllama`** é a classe do LangChain que fala com o Ollama. Ela existe para dar ao
modelo local a mesma interface de um modelo de nuvem — trocar para Claude ou GPT seria
trocar esta classe, e o resto do projeto não saberia.

Parâmetro por parâmetro:

| Parâmetro | O que faz | Por que este valor |
|---|---|---|
| `reasoning=False` | desliga o modo de raciocínio do qwen3 | O `<think>` gasta segundos e centenas de tokens para escolher entre 6 opções. Para classificação com enum, é puro custo. |
| `format=schema` | ativa a decodificação restrita | É a trava descrita acima |
| `num_predict=128` | máximo de tokens na resposta | A resposta é `{"action": "click"}` — uns 10 tokens. O teto impede o modelo de entrar em loop e travar o chat. |
| `temperature=0` | sem sorteio | mesmo comando → mesma decisão |

> Por que criar o `ChatOllama` **dentro** da função, a cada chamada, em vez de reusar?
> Porque o `format` muda: a pergunta da ação usa um enum, a do elemento usa outro. O
> objeto é barato (é só configuração; o modelo fica carregado no processo do Ollama), e
> a alternativa — um cache por schema — seria complexidade sem ganho perceptível.

```python
50      messages: list[BaseMessage] = [SystemMessage(content=system)]
51      for example_in, example_out in examples:
52          messages.append(HumanMessage(content=example_in))
53          messages.append(AIMessage(content=example_out))
54      messages.append(HumanMessage(content=user))
```
Monta a conversa. Os três tipos de mensagem do LangChain:

- **`SystemMessage`** — a instrução: quem você é, o que deve fazer;
- **`HumanMessage`** — o que o usuário diz;
- **`AIMessage`** — o que a IA respondeu.

O laço das linhas 51–53 é a técnica de **few-shot prompting**: eu **finjo** que a
conversa já aconteceu, alternando pergunta e resposta perfeita. O modelo, que só sabe
continuar padrões, vê cinco pares bem formados e continua no mesmo formato.

**Por que few-shot em vez de mais instrução:** modelos pequenos aprendem muito melhor
por exemplo do que por regra. Escrever "responda sempre com o nome exato da ação" numa
frase funciona pior do que mostrar cinco vezes o comportamento certo.

```python
56      response = await llm.ainvoke(messages, config={"run_name": run_name})
57      raw = _THINK_RE.sub("", str(response.content)).strip()
58      try:
59          parsed = json.loads(raw)
60      except json.JSONDecodeError:
61          return {}
62      return parsed if isinstance(parsed, dict) else {}
```
`ainvoke` manda a conversa e espera a resposta (versão assíncrona, para não bloquear o
servidor). O `run_name` vira o nome do span no LangSmith — é por isso que lá você vê
`escolher_acao` e `escolher_elemento` separados, e não duas chamadas idênticas.

Linhas 58–62: parse defensivo. Em teoria a decodificação restrita garante JSON válido;
na prática, uma versão diferente do Ollama ou um timeout podem devolver outra coisa.
**Retornar `{}` em vez de levantar exceção** é deliberado: quem chama já trata "não veio
nada" com um fallback, e um `{}` produz uma resposta útil em vez de um stacktrace.

A linha 62 confere que veio mesmo um dicionário — um JSON válido poderia ser uma lista.

## 6.2 Pergunta 1: que ação é esta?

```python
24  ACTION_SYSTEM = (
25      "Classifique a acao de UM comando de teste web.\n"
26      "goto = abrir uma URL, acessar um site\n"
27      "fill = digitar, informar ou preencher um valor em um campo\n"
28      "click = clicar ou pressionar um botao ou link\n"
29      "expect_text = validar, verificar ou conferir que algo e apresentado na tela;\n"
30      "  so vale quando o comando diz qual texto deve aparecer\n"
31      "locate = apenas localizar ou identificar um campo, sem interagir com ele\n"
32      "Responda apenas com o JSON."
33  )
```
O prompt de sistema inteiro. **Oito linhas.** Isso é proposital.

A palavra **"UM"** em maiúsculas está lá porque o modelo tende a tentar processar a frase
toda quando vê várias ações. Como o `split_commands` já garantiu que chega um comando
por vez, eu reforço isso na instrução.

Cada ação tem uma definição de uma linha **com sinônimos em português**, porque você vai
escrever "aperte", "pressione", "clique" — e o modelo precisa mapear todos para `click`.

A linha 30 é a restrição que depois vira código (`parece_validacao`): *"só vale quando o
comando diz qual texto deve aparecer"*. Dizer no prompt reduz o erro; a trava em Python
elimina o que sobra.

> Repare o que **não** está no prompt: exemplos de saída errada, ameaças ("é MUITO
> IMPORTANTE"), explicação do domínio. Num modelo de 1.7B, cada palavra a mais é ruído
> disputando atenção com as que importam.

```python
35  ACTION_EXAMPLES = [
36      ("COMANDO: Abrir o site https://exemplo.com", '{"action": "goto"}'),
37      ("COMANDO: Localizar o campo Telefone.", '{"action": "locate"}'),
38      ("COMANDO: Preencher o campo Nome com Joao", '{"action": "fill"}'),
39      ("COMANDO: Pressionar o botao Enviar", '{"action": "click"}'),
40      ("COMANDO: Verificar que a tela exibe Cadastro concluido", '{"action": "expect_text"}'),
41      # "confirmacao" puxa o modelo para expect_text; este exemplo desfaz isso.
42      ("COMANDO: Informe a confirmacao da senha Teste@123", '{"action": "fill"}'),
43      ("COMANDO: Apague o que esta no campo Nome", '{"action": "clear"}'),
44      ("COMANDO: limpe o campo", '{"action": "clear"}'),
45  ]
```
Os oito exemplos. Os cinco primeiros cobrem uma ação cada. **Os três últimos existem
porque erros reais aconteceram:**

- Linha 42 — o caso "confirmação". O modelo via a palavra e ia para `expect_text`. Este
  exemplo mostra o contrário no contexto exato.
- Linhas 43–44 — duas formas de dizer "limpe", uma longa e uma curta. Duas porque o
  modelo confundia `clear` com `fill` (as duas mexem num campo de texto).

O prefixo `COMANDO:` em todos é um detalhe que importa: **formato consistente**. O
modelo aprende que depois de `COMANDO: <algo>` vem um JSON, e a entrada real (linha 52)
usa o mesmo prefixo.

```python
48  async def choose_action(text: str) -> Action:
49      result = await classify(
50          system=ACTION_SYSTEM,
51          examples=ACTION_EXAMPLES,
52          user=f"COMANDO: {text}",
53          schema=enum_schema(action=[a.value for a in Action]),
54          run_name="escolher_acao",
55      )
56      try:
57          return Action(result.get("action", ""))
58      except ValueError:
59          return Action.LOCATE
```
Linha 53: o enum é gerado **a partir da classe `Action`**. Se eu acrescentar uma ação
nova em `models.py`, o schema se atualiza sozinho — impossível esquecer.

Linhas 56–59: `Action("click")` converte a string no membro do enum, e levanta
`ValueError` se não existir. O fallback é **`LOCATE`** — escolhido a dedo por ser a
**única ação inofensiva**: ela olha e reporta, não clica nem digita. Em caso de dúvida,
o agente não age.

## 6.3 A trava de validação

```python
62  _VERBOS_DE_VALIDACAO = re.compile(
63      r"\b(?:valid\w*|verifi(?:c|qu)\w*|confir\w*|confer\w*|che(?:c|qu)\w*)\b",
64      re.IGNORECASE,
65  )
```
Os radicais dos verbos de validação. Anatomia:

- `\b` — *word boundary*, a fronteira de palavra. Impede casar no meio de outra palavra.
- `(?: ... )` — grupo **sem captura**. Agrupa sem guardar; mais rápido e mais claro.
- `verifi(?:c|qu)\w*` — o detalhe do português: **verifi**car / **verifi**que. O radical
  alterna entre `c` e `qu` na conjugação. `verific\w*` sozinho **não casaria com
  "verifique"** — esse foi um bug de verdade neste projeto (o mesmo aconteceu com
  "clicar/clique").
- `\w*` — qualquer terminação: valid**ar**, valid**e**, valid**ando**.

```python
68  def parece_validacao(text: str) -> bool:
76      if find_quoted(text) or ":" in text:
77          return True
78      return bool(_VERBOS_DE_VALIDACAO.search(text))
```
Duas evidências, e qualquer uma basta:

1. **Há texto entre aspas ou depois de dois-pontos** — você está indicando *qual* texto
   espera. Só se faz isso para validar.
2. **Há um verbo de validação.**

Se nenhuma aparece, o que a LLM viu foi o nome do campo, não uma ordem de conferir.

## 6.4 Pergunta 2: qual elemento?

```python
92  async def choose_element(text: str, elements: list[PageElement]) -> PageElement | None:
93      if not elements:
94          return None
96      catalog = "\n".join(f"{e.element_id} = {e.describe()}" for e in elements)
```
Monta o catálogo. Na prática, para a tela de login do BugBank:

```
E1 = textbox "Informe seu e-mail" [Acessar]
E2 = textbox "Informe sua senha" [Acessar]
E3 = button "Acessar" [Acessar]
E4 = button "Registrar" [Acessar]
```

**Agora eu respondo diretamente àquela sua pergunta:** *"o LLM lê todo o html e js da
página?"*

**Não. E é exatamente por isso que funciona.**

O HTML do BugBank tem dezenas de milhares de caracteres — CSS, bundles React, atributos
gerados. Isso não caberia na janela de contexto, e se coubesse, afogaria o modelo em
ruído. O que ele recebe são **quatro linhas**, cada uma com papel, nome e formulário.

Quem lê o HTML é o **JavaScript determinístico** que roda dentro da página
(`_COLLECT_JS`, Parte 8). Ele percorre o DOM, aplica regras de visibilidade e produz
essa lista. A LLM só faz a parte que é linguagem: casar *"clique em acessar"* com
*"button Acessar"*.

```python
97      system = (
98          "Escolha qual elemento da pagina o comando utiliza.\n\n"
99          f"ELEMENTOS DISPONIVEIS:\n{catalog}\n\n"
100         f"Responda apenas com o JSON, usando um dos ids acima ou {NO_ELEMENT}."
101     )
102     valid = [e.element_id for e in elements]
104     result = await classify(
105         system=system,
106         examples=[],
107         user=f"COMANDO: {text}",
108         schema=enum_schema(element=valid + [NO_ELEMENT]),
109         run_name="escolher_elemento",
110     )
```
Linha 106: **`examples=[]`** — sem few-shot aqui. Motivo: os ids mudam a cada página, e
um exemplo com `E3` de outra tela ensinaria o modelo a preferir `E3` por hábito. A tarefa
também é mais simples (casar texto com texto) e o catálogo já é o contexto.

Linha 108: o enum é construído **a partir dos ids reais desta página, agora**. É a
**Regra 3** virando mecanismo: não existe token válido para um elemento que não está na
tela. O `NO_ELEMENT` ("NENHUM") dá ao modelo uma saída honesta.

```python
112     chosen = result.get("element")
113     by_id = {e.element_id: e for e in elements}
114     if chosen in by_id and _plausible(text, by_id[chosen]):
115         return by_id[chosen]
116     return _fuzzy(text, elements)
```
Linha 113 monta um índice id → elemento, para a busca ser direta.

Linha 114 exige **duas** coisas: o id existe **e** a escolha é plausível. É o próximo
tópico.

## 6.5 `_plausible` — desconfiar da resposta

```python
119 def _plausible(text: str, element: PageElement) -> bool:
128     return bool(tokens(text) & tokens(element.name))
```
Uma linha, e resolve um problema fundamental de trabalhar com enum.

**O problema:** a decodificação restrita garante que a resposta é um id válido. Mas
"válido" não é "certo". O modelo **não tem como dizer "não sei"** de forma natural — a
força do mecanismo é também a fraqueza dele. Quando pedimos *"clicar no botão
Transferência"* numa página que não tinha esse botão, ele respondeu **"Cadastrar"**. E o
agente clicou.

**A solução:** exigir pelo menos **uma palavra em comum** entre o seu comando e o nome do
elemento. `tokens()` (Parte 12) normaliza — sem acento, minúsculo, só palavras com mais
de 2 letras — e `&` é a interseção de conjuntos.

- `"clicar no botão Acessar"` ∩ `"Acessar"` → `{acessar}` → ✅ plausível
- `"clicar no botão Transferência"` ∩ `"Cadastrar"` → `{}` → ❌ vira "não achei"

Isso transforma um palpite silencioso numa resposta honesta. **Errar de forma visível é
muito melhor do que acertar por sorte.**

## 6.6 `_fuzzy` — a rede embaixo

```python
81  def _fuzzy(text: str, elements: list[PageElement]) -> PageElement | None:
83      wanted = tokens(text)
84      best, best_score = None, 0
85      for element in elements:
86          score = len(wanted & tokens(f"{element.name} {element.input_type}"))
87          if score > best_score:
88              best, best_score = element, score
89      return best
```
Se a LLM não devolveu id válido (ou a escolha foi implausível), tentamos **sem IA
nenhuma**: conta quantas palavras cada elemento tem em comum com o comando e fica com o
melhor.

Linha 86: o `input_type` entra no saco. Assim `"informe a senha"` casa com um
`<input type="password">` mesmo que o rótulo dele seja outro.

Linha 87 usa `>` e não `>=`: em empate, **o primeiro da página vence**. Ordem de DOM é
ordem visual, e o primeiro campo é o mais provável.

Se ninguém tem palavra em comum, `best` continua `None` → nó `faltou_elemento`.

## 6.7 `disambiguate` — dois formulários, o mesmo campo

```python
131 def disambiguate(
132     chosen: PageElement | None,
133     elements: list[PageElement],
134     active_form: str,
135 ) -> PageElement | None:
145     if chosen is None or not chosen.form:
146         return chosen
148     twins = [e for e in elements if e.name == chosen.name and e.role == chosen.role]
149     if len(twins) < 2:
150         return chosen
152     if active_form:
153         for twin in twins:
154             if twin.form == active_form:
155                 return twin
156     return twins[0]
```
**O problema:** no BugBank, login e cadastro coexistem no DOM. Os dois têm "Informe seu
e-mail" e "Informe sua senha". Olhando só para `"informe o e-mail x@y.com"` isolado, a
escolha é ambígua **até para uma pessoa**.

**A solução, em duas regras:**

- Linha 148 — acha os "gêmeos": mesmo nome, mesmo papel. Se só existe um, não há
  problema (linha 149).
- Linhas 152–155 — **se você já interagiu com um formulário, é nele que está
  trabalhando.** É contexto de conversa, mantido em `session.active_form`, sem gastar
  prompt.
- Linha 156 — sem contexto, o primeiro da página. É o que uma pessoa faria ao abrir a
  tela.

Repare: isto é **determinístico**. Eu poderia ter mandado o formulário no prompt e pedido
para a LLM decidir. Seria mais lento, menos confiável e impossível de depurar. A **Regra
1** diz para dar à LLM só o que é linguagem — e "em qual formulário eu estava" é estado,
não linguagem.

## 6.8 `only_text_field`

```python
159 def only_text_field(elements: list[PageElement]) -> PageElement | None:
165     campos = [e for e in elements if e.editable]
166     return campos[0] if len(campos) == 1 else None
```
Para comandos que **não nomeiam o campo**: `"digite banana"` no Google.

Se a página tem exatamente **um** campo editável, não há o que desambiguar. Se tem dois
ou mais, retorna `None` — adivinhar seria pior que perguntar.

O `editable` é o flag calculado no JavaScript (Parte 8.4), e ele existe por causa de um
bug que você encontrou: a caixa de busca do Google é uma `<textarea role="combobox">`.
Eu classificava pelo papel ARIA, então ela não era vista como campo de texto e o agente
"não achava a barra de pesquisa".

---

# Parte 7 — O valor literal (`literals.py`)

Este arquivo inteiro existe por causa de **uma** falha medida:

> Pedi para o `qwen3:1.7b` copiar `qualquerCoisa0001@gmail.com` do cenário.
> Ele devolveu `anything0001@gmail.com`. **Traduziu.**

Um modelo de linguagem é treinado para produzir texto *plausível*, não para copiar. Um
e-mail que contém uma palavra em português é uma tentação irresistível. E o erro é
silencioso: o teste roda, o login falha, e você passa uma hora procurando bug na
aplicação.

Daí a **Regra 2**: nenhum valor passa pela LLM. Todos são recortados por regex.

## 7.1 As regexes do topo

```python
16  URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
```
`https?` — o `?` faz o `s` opcional, cobrindo http e https. Depois, tudo que **não** for
espaço, aspas, `<`, `>`, `)` ou `]`. Definir pelo que **para** a URL é mais robusto do
que tentar listar tudo que pode aparecer dentro dela.

```python
17  BARE_DOMAIN_RE = re.compile(r"(?<![@\w.])((?:[\w-]+\.)+[a-z]{2,})(/\S*)?", re.IGNORECASE)
```
Para quando você digita `bugbank.netlify.app` sem o `https://`.

`(?<![@\w.])` é um **lookbehind negativo**: "não case se logo antes vier `@`, letra ou
ponto". É o que impede a parte `gmail.com` de um e-mail ser confundida com domínio.

`(?:[\w-]+\.)+` são os rótulos seguidos de ponto, um ou mais. `[a-z]{2,}` é o TLD.

```python
18  EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
19  QUOTED_RE = re.compile(r"[\"“”]([^\"“”]{2,})[\"“”]")
```
A linha 19 aceita **três** tipos de aspas: reta e as duas curvas. Motivo prático: se
você escrever o comando no Word, no WhatsApp ou copiar de um documento, vêm aspas
curvas. Aceitar só a reta faria a validação falhar por um motivo invisível.

O `{2,}` exige ao menos 2 caracteres dentro, e os parênteses criam o **grupo de
captura** — `m.group(1)` devolve o conteúdo **sem** as aspas.

```python
22  MARKER_RE = re.compile(
23      r"\b(?:digite|digitar|digito|escreva|escrever|preencha|preencher|"
24      r"informe|informar|insira|inserir|coloque|colocar|com|valor|texto)\b",
25      re.IGNORECASE,
26  )
```
Verbos que **anunciam** que o valor vem logo em seguida. A ideia: em português, o valor
quase sempre vem depois de um desses.

## 7.2 As listas de exclusão

```python
31  _FILLER = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "no", "na", "em",
32             "campo", "valor", "texto", "seguinte", "barra"}
```
Artigos e preposições que ficam entre o verbo e o valor: em `"digite o nome Joao"`, o
`"o"` precisa ser descartado.

```python
35  _NOT_A_VALUE = {
36      "campo", "senha", "email", "e-mail", "valor", "botao", "botão",
37      "aplicacao", "aplicação", "tela", "pagina", "página", "modal", "mensagem",
38      "pesquisa", "pesquisar", "busca", "buscar",
39      # cortesia que sobra no fim da frase
40      "favor", "obrigado", "obrigada", "beleza", "valeu", "please",
41  }
```
Palavras que são **rótulo**, nunca valor. Sem isso, `"preencha o campo senha"` (sem valor)
produziria a senha `"senha"` — e o teste passaria preenchendo lixo.

As palavras de cortesia estão aí porque o extrator de último recurso pega a **última
palavra** da frase. Em `"informe o e-mail x@y.com, por favor"`, sem esta lista o valor
seria `"favor"`.

## 7.3 `_has_symbol` — o sinal mais forte

```python
67  _SIMBOLOS_DE_DADO = set(r"@#$%&*_/+\|~^")
70  def _has_symbol(token: str) -> bool:
77      return any(char.isdigit() or char in _SIMBOLOS_DE_DADO for char in token)
```
**A heurística central:** se a palavra tem dígito ou símbolo, é quase certamente um dado
de teste. `Teste@123`, `ABC-99`, `joao99` — nomes de campo não são assim.

O comentário do código guarda a razão de **vírgula e ponto ficarem de fora**:

```python
74      Virgula e ponto ficam de fora de proposito: eles sao pontuacao de frase, e
75      aceita-los fazia "nome, por favor" passar por valor.
```

Note o `r"..."` — string **crua**. Sem ele, a barra invertida seria interpretada como
escape pelo Python. Isso me mordeu neste projeto: um `\b` numa string normal virou o
caractere *backspace* e matou uma regex em silêncio.

## 7.4 `_echoes_label` — o candidato é só o nome do campo?

```python
80  def _echoes_label(token: str, label: str) -> bool:
82      if not label:
83          return False
84      candidate = normalize(token)
85      for word in tokens(label):
86          if candidate == word:
87              return True
88          if len(candidate) >= 4 and (candidate.startswith(word[:4]) or word.startswith(candidate[:4])):
89              return True
90      return False
```
Detecta quando o "valor" extraído é só o nome do campo repetido.

A linha 88 é uma comparação de **radical**: se os 4 primeiros caracteres batem, é a mesma
palavra em outra forma. É assim que `"pesquisa"` é reconhecido como eco do campo
`"Pesquisar"`, e `"confirmação"` do campo `"Informe a confirmação da senha"`.

Quatro caracteres é um equilíbrio medido: menos gera falso positivo (`"Ana"` × `"Anexo"`),
mais deixa passar variação curta.

> **Contexto:** minha primeira versão descartava qualquer palavra toda em minúsculas
> sem símbolo. Isso fez `"digite banana"` falhar — `banana` é um valor perfeitamente
> legítimo. A regra estava olhando para a forma da palavra; o certo é olhar para a
> **relação dela com o nome do campo**. Esta função é a correção.

## 7.5 `_acceptable` — o filtro, e a ordem dele

```python
97  def _acceptable(token: str | None, element_label: str) -> str | None:
99      if not token:
100         return None
101     if _has_symbol(token):
102         # Teste@123, joao99 -- e tambem "4", o digito da conta: um unico caractere
103         # pode ser um valor legitimo, entao o teste de tamanho vem depois deste.
104         return token
105     if len(token) < 2:
106         return None
107     if normalize(token) in {normalize(w) for w in _NOT_A_VALUE} or normalize(token) in _CORTESIA:
108         return None
109     if _echoes_label(token, element_label):
110         return None
111     return token
```
**A ordem das verificações é o comportamento.** Isto é um bug corrigido.

Antes, o teste de tamanho (linha 105) vinha **antes** do teste de símbolo. Resultado:
`"informe o dígito da conta 4"` era rejeitado, porque `"4"` tem um caractere só. Mas um
dígito verificador de conta **é** um valor de um caractere.

Colocando o `_has_symbol` primeiro, qualquer coisa com dígito ou símbolo é aceita
imediatamente, e o filtro de tamanho só se aplica a palavras puramente alfabéticas — onde
ele faz sentido ("o", "a" não são valores).

## 7.6 As três estratégias de extração

São tentadas **em ordem**, da mais confiável para a mais desesperada.

```python
114 def _after_comma(text: str) -> str | None:
121     if "," not in text:
122         return None
123     cauda = text.rsplit(",", 1)[1].strip().strip(_TRAILING)
124     palavras = cauda.split()
125     if not (2 <= len(palavras) <= 5):
126         return None
```
**Estratégia 1 — depois da vírgula.** Para valores de várias palavras:
`"coloque no email o seguinte texto, banana pera uva"` → `"banana pera uva"`.

`rsplit(",", 1)` quebra na **última** vírgula. A janela de 2 a 5 palavras é deliberada:
uma palavra só o `_trailing_token` já pega, e mais de cinco quase certamente é o resto
da frase, não um valor.

```python
137 def _after_marker(text: str, element_label: str = "") -> str | None:
147     markers = list(MARKER_RE.finditer(text))
148     if not markers:
149         return None
151     words = [w for w in (p.strip(_TRAILING) for p in text[markers[-1].end():].split()) if w]
152     while words and not _has_symbol(words[0]) and (
153         words[0].lower() in _FILLER or _echoes_label(words[0], element_label)
154     ):
155         words.pop(0)
156     if not words:
157         return None
158     # Sobrou uma frase inteira? Entao o valor e so a primeira palavra dela.
159     return " ".join(words) if len(words) <= 3 else words[0]
```
**Estratégia 2 — depois do verbo.** A mais usada.

Linha 147: `markers[-1]` é o **último** marcador. Em `"informe o valor com Joao"` há dois
(`informe`, `com`) e o valor vem depois do último.

Linhas 152–155: o laço que descarta o começo. Ele remove, palavra por palavra:
- artigos e preposições (`_FILLER`), e
- **o próprio nome do campo** (`_echoes_label`).

Isso resolve `"informe o nome Vinicius Gentile"`: descarta `"o"`, descarta `"nome"`
(que ecoa o campo "Nome"), e sobra `"Vinicius Gentile"`. Sem esse laço o valor virava
só `"Gentile"` — errado e silencioso, o pior tipo de bug.

O `not _has_symbol(words[0])` protege: se a palavra tem símbolo, é dado, nunca
descartar — mesmo que pareça eco.

Linha 159: até 3 palavras, o valor é a frase toda (nomes compostos). Acima disso,
provavelmente pegamos frase demais, então fica só a primeira palavra.

```python
132 def _trailing_token(text: str) -> str | None:
133     tokens_ = text.strip().split()
134     return tokens_[-1].strip(_TRAILING) if tokens_ else None
```
**Estratégia 3 — a última palavra.** O último recurso, e funciona mais do que parece:
em português a gente naturalmente termina o comando com o valor. É esta que depende mais
do `_acceptable` para não devolver lixo.

## 7.7 `extract_value` — o despachante

```python
162 def extract_value(text: str, action: str, *, element_label: str = "") -> str | None:
164     if action == "goto":
165         return find_url(text)
167     if action == "fill":
168         email = EMAIL_RE.search(text)
169         if email:
170             return email.group(0)
171         for quoted in find_quoted(text):
172             if not _echoes_label(quoted, element_label):
173                 return quoted
174         return (
175             _acceptable(_after_comma(text), element_label)
176             or _acceptable(_after_marker(text, element_label), element_label)
177             or _acceptable(_trailing_token(text), element_label)
178         )
```
A ordem é uma **escada de confiança**:

1. **E-mail** (linha 168) — um e-mail é inconfundível. Se existe um no texto, é o valor.
2. **Aspas** (171) — você marcou explicitamente. A única ressalva é não aceitar aspas que
   só repetem o nome do campo.
3. **As três estratégias** (174–178), encadeadas com `or`. Em Python, `or` devolve o
   primeiro valor "verdadeiro" — então isto é "tente 1, senão 2, senão 3", e cada
   resultado passa pelo filtro `_acceptable` antes de contar.

```python
180     if action == "expect_text":
181         quoted = find_quoted(text)
182         if quoted:
183             return max(quoted, key=len)  # a mensagem esperada e a maior das aspas
184         return _after_colon(text)
186     return None
```
Para validação, `max(..., key=len)` pega **a maior** citação. Se você escreveu
`Validar que aparece "Erro" na tela: "Usuário ou senha inválido..."`, a mensagem
esperada é a longa.

Linha 186: `click`, `locate` e `clear` não têm valor. Retornam `None`.

## 7.8 Máscaras — validar mensagem com dado variável

Esta parte nasceu do seu pedido: validar `"A conta XXXX-X foi criada com sucesso"`,
onde o número da conta muda a cada execução.

```python
198 _CURINGA = set("Xx#*.…_-")
199 _CURINGA_FORTE = set("Xx#*…")
202 def _e_mascara(palavra: str) -> bool:
203     limpa = palavra.strip(".,;:!?()[]")
204     if not limpa or not all(c in _CURINGA for c in limpa):
205         return False
206     # Precisa de pelo menos dois curingas, senao um hifen solto viraria mascara.
207     return sum(1 for c in limpa if c in _CURINGA_FORTE) >= 2
```
**Dois conjuntos, e a diferença entre eles é a proteção.**

`_CURINGA` é o que **pode** compor uma máscara — inclui hífen e ponto porque `XXXX-X` e
`###.###` são formatos comuns.

`_CURINGA_FORTE` exclui hífen e ponto. E a linha 207 exige **pelo menos dois** curingas
fortes. Sem isso, um hífen solto numa frase ("cadastro - sucesso") viraria máscara e a
validação aceitaria qualquer coisa naquela posição. A validação ficaria frouxa **sem
ninguém perceber**, que é o pior resultado possível para um teste.

```python
214 def to_pattern(texto: str) -> re.Pattern[str] | None:
216     if not tem_mascara(texto):
217         return None
219     partes = []
220     for palavra in texto.split():
221         if _e_mascara(palavra):
222             partes.append(r"\S+")
223         else:
224             partes.append(re.escape(palavra))
225     # \s+ entre as palavras: a aplicacao pode quebrar a mensagem em varias linhas.
226     return re.compile(r"\s+".join(partes), re.IGNORECASE)
```
Converte a máscara em regex, palavra por palavra:

- palavra que é máscara → `\S+` (um ou mais não-espaços: qualquer "palavra");
- palavra normal → `re.escape(palavra)`.

**`re.escape` é essencial.** Ele neutraliza os caracteres especiais de regex. Sem ele, um
`!` ou `(` na mensagem esperada mudaria o significado do padrão, ou faria a compilação
falhar. A mensagem de erro do BugBank termina em `!` — sem `re.escape`, quebraria.

O `\s+` na junção permite que a aplicação quebre a mensagem em várias linhas. O BugBank
faz exatamente isso no modal de erro.

Resultado, para `"A conta XXXX-X foi criada com sucesso"`:

```
A\s+conta\s+\S+\s+foi\s+criada\s+com\s+sucesso
```

**A validação não afrouxou** — "A conta", "foi criada com sucesso" continuam sendo
comparados letra por letra. Só o trecho imprevisível virou curinga.

`return None` quando não há máscara (linha 217) é o que mantém o comportamento antigo
intacto: sem máscara, comparação literal de sempre.

---

# Parte 8 — O browser executa (`browser.py`)

Este é o arquivo mais importante do projeto, e o que mais me deu trabalho. É aqui que
mora a resposta completa para a sua pergunta sobre como o Playwright acha os elementos.

## 8.1 Por que a API assíncrona do Playwright

O Playwright em Python tem **duas** APIs: `sync_playwright` e `async_playwright`.

A síncrona é mais simples de escrever. Mas ela **não pode** ser usada dentro de um
servidor assíncrono — ela detecta que existe um *event loop* rodando e levanta um erro
explícito. E se você tentar contornar rodando numa thread separada, os objetos do
Playwright não podem atravessar threads.

Como o FastAPI é assíncrono, a escolha foi feita por ele. Daí todo método aqui ser
`async def` e toda chamada ter `await`.

## 8.2 A sessão viva

```python
201 class BrowserSession:
204     def __init__(self) -> None:
205         self._playwright = None
206         self._browser = None
207         self._page: Page | None = None
208         self.elements: list[PageElement] = []
210         self.active_form: str = ""
213         self.last_element: PageElement | None = None
```
Os três primeiros com `_` são privados — a mecânica do Playwright. Os três públicos são
o **estado do agente**:

- `elements` — o inventário da tela atual. É o que a LLM vê.
- `active_form` — em qual formulário você está trabalhando (Parte 6.7).
- `last_element` — o último elemento tocado. A única memória de conversa.

```python
217     @property
218     def is_open(self) -> bool:
219         return self._page is not None and not self._page.is_closed()
```
`@property` faz `session.is_open` ser lido como atributo, mas calculado na hora.

As **duas** condições importam: a página pode existir como objeto e já ter sido fechada
(você clicou no X do Chromium). Checar só `is not None` daria falso positivo e o próximo
comando estouraria com um erro obscuro.

```python
225     async def _ensure_page(self) -> Page:
226         if self.is_open:
227             return self._page
228         self._playwright = await async_playwright().start()
229         self._browser = await self._playwright.chromium.launch(headless=settings.headless)
230         context = await self._browser.new_context(viewport={"width": 1280, "height": 800})
231         self._page = await context.new_page()
232         return self._page
```
**Inicialização preguiçosa:** o browser só abre no primeiro comando que precisa dele.
Você sobe o servidor e nenhum Chromium aparece até você mandar uma URL.

A hierarquia do Playwright, que vale entender:

| Objeto | O que é |
|---|---|
| `playwright` | o processo driver que fala com os navegadores |
| `browser` | o Chromium em si |
| `context` | um perfil isolado — cookies, localStorage e sessão próprios |
| `page` | uma aba |

**Por que o `context` no meio:** ele é a unidade de isolamento. Criar um contexto novo é
barato e dá uma sessão limpa, sem cookies do teste anterior. Abrir um browser inteiro
seria lento; usar a aba padrão sem contexto misturaria estado entre execuções.

`viewport={"width": 1280, "height": 800}` fixa o tamanho da janela. **Isso não é
estético:** o inventário depende de geometria (Parte 8.4 usa `elementFromPoint`), e sites
responsivos mudam de layout com a largura. Tamanho fixo = comportamento reproduzível.

```python
234     async def close(self) -> None:
235         if self._browser:
236             await self._browser.close()
237         if self._playwright:
238             await self._playwright.stop()
239         self._playwright = self._browser = self._page = None
240         self.elements = []
241         self.active_form = ""
242         self.last_element = None
```
Desmonta na ordem inversa e **zera o estado do agente também**. Esquecer as linhas
240–242 deixaria o inventário de uma página que não existe mais — e o agente tentaria
clicar em fantasmas.

## 8.3 Esperar a página parar de mudar

Esta é a correção do último bug que você reportou: *"mudou de página de novo e ele deu
isso aqui"*.

```python
24  # Esperar um tempo fixo depois de cada acao e uma corrida perdida: medimos o BugBank
25  # trocando de tela entre 101ms e 376ms depois do mesmo clique. Amostrar a pagina de
26  # tempos em tempos tambem falha, porque uma pausa entre dois renders parece "estavel".
31  SETTLE_PASSO_MS = 100     # intervalo entre consultas
32  SETTLE_MINIMO_MS = 400    # nunca decide antes disso
33  SETTLE_QUIETO_MS = 500    # tempo sem nenhuma mutacao para considerar pronta
34  SETTLE_LIMITE_MS = 5000   # teto, para pagina que nunca para (spinner, carrossel)
```
**A história, porque ela ensina mais que o código.**

Eu comecei com uma espera fixa de 400ms depois de cada ação. Funcionava… às vezes. Aí
eu medi de verdade, com um script que amostrava a página a cada 50ms depois do clique de
login:

```
     44ms  MUDOU -> https://bugbank.netlify.app/      | 14 elementos
    101ms  MUDOU -> https://bugbank.netlify.app/home  |  6 elementos
```

E numa outra execução, **o mesmo clique**, levou **376ms**. Variação de 3,7× por causa de
rede, cache e carga da máquina. Qualquer número fixo está errado em metade das vezes — e
o sintoma é cruel: o agente lê a tela **anterior** e responde com confiança usando
elementos que não estão mais lá.

Segunda tentativa: amostrar a página e parar quando ela "estabilizar". Também falhou —
uma pausa entre dois renders parece estabilidade.

**A solução é deixar o navegador avisar.**

```javascript
39  _MUTACAO_JS = """
40  () => {
41    if (window.__qaiMut === undefined) {
42      window.__qaiMut = Date.now();
43      const obs = new MutationObserver(() => { window.__qaiMut = Date.now(); });
44      obs.observe(document.documentElement, {
45        childList: true, subtree: true, attributes: true, characterData: true,
46      });
47    }
48    return Date.now() - window.__qaiMut;
49  }
50  """
```
**`MutationObserver`** é uma API nativa do navegador que dispara um callback **toda vez
que o DOM muda**. É o mesmo mecanismo que o React usa para saber quando algo mudou.

Linha 41: `if (... === undefined)` instala **uma vez por documento**. Chamar o JS de
novo só lê o contador.

Linhas 44–46, as quatro opções do `observe`:
- `childList` — elementos adicionados ou removidos;
- `subtree` — observar a árvore inteira, não só os filhos diretos;
- `attributes` — mudanças de atributo (classe, style — é assim que se detecta o card
  virando);
- `characterData` — mudanças de texto.

Juntas: **qualquer** alteração na página atualiza o carimbo de tempo.

Linha 48: devolve **há quantos milissegundos nada muda**.

E o detalhe elegante, que está no comentário do código (linhas 36–38): depois de uma
navegação de verdade, o `window` é **novo**. O observador se reinstala sozinho e o
contador volta a zero — que é exatamente o certo, porque acabou de mudar tudo.

```python
375     async def _settle(self) -> None:
377         page = self._page
378         if page is None:
379             return
381         gasto = 0
382         while gasto < SETTLE_LIMITE_MS:
383             try:
384                 quieto_ha = await page.evaluate(_MUTACAO_JS)
385             except Exception:  # noqa: BLE001 - navegando; ainda nao esta pronta
386                 quieto_ha = 0
388             if gasto >= SETTLE_MINIMO_MS and quieto_ha >= SETTLE_QUIETO_MS:
389                 return
391             await page.wait_for_timeout(SETTLE_PASSO_MS)
392             gasto += SETTLE_PASSO_MS
```
O laço. Três travas, e cada uma tem um motivo:

- **`SETTLE_MINIMO_MS = 400`** (linha 388) — nunca decide antes de 400ms. Protege contra
  uma janela em que o clique foi processado mas a SPA ainda não começou a re-renderizar;
  nesse instante o DOM está genuinamente quieto, mas pelo motivo errado.
- **`SETTLE_QUIETO_MS = 500`** — precisa de meio segundo de silêncio. Um render em duas
  fases (React costuma fazer isso) tem uma pausa curta no meio; 500ms atravessa ela.
- **`SETTLE_LIMITE_MS = 5000`** (linha 382) — teto absoluto. Uma página com spinner ou
  carrossel **nunca** fica quieta; sem o teto, o agente travaria para sempre.

Linhas 383–386: durante uma navegação, `page.evaluate` falha porque o contexto de
execução foi destruído. Isso **não** é erro — é sinal de que a página está mudando
agora mesmo. Tratamos como "0ms de silêncio" e continuamos esperando.

`page.wait_for_timeout(ms)` é a pausa do Playwright. Uso ela em vez de `asyncio.sleep`
porque ela é integrada ao laço de eventos do browser.

**Verificação:** depois dessa mudança, rodei o fluxo completo três vezes seguidas, e as
três leram a tela certa em cada transição — login → home → transferência → home.

## 8.4 Ler a página: `_COLLECT_JS`

Aqui está a resposta completa àquela sua pergunta. **O JavaScript abaixo roda dentro da
página, no Chromium** — não no Python. Ele é o "olho" do agente.

### A primeira varredura: elementos semânticos

```javascript
58    const SEMANTICOS = 'input, button, select, textarea, a[href], [role="button"]';
```
Os elementos que são interativos **por definição do HTML**.

### A segunda varredura: os que só *parecem* botão

```javascript
65    const soltos = Array.from(document.querySelectorAll('div, span, p, li, a')).filter((el) => {
66      if (el.matches(SEMANTICOS)) return false;   // ja entrou pela porta da frente
67      if (getComputedStyle(el).cursor !== 'pointer') return false;
68      if (el.querySelector(SEMANTICOS)) return false;          // tem um de verdade dentro
69      const texto = (el.innerText || '').trim();
70      if (texto.length > 40) return false;
73      if (!texto && !el.id && !el.getAttribute('aria-label')) return false;
75      return !Array.from(el.querySelectorAll('*')).some(
76        (filho) => getComputedStyle(filho).cursor === 'pointer' && (filho.innerText || '').trim()
77      );
78    });
```
**Por que existe:** o modal do BugBank fecha num `<a id="btnCloseModal">` — âncora **sem
href**. Ele não casa com `a[href]`, não é `<button>`, não tem `role`. Pelas regras
semânticas ele simplesmente **não existe** — e o agente respondia "não achei o botão
Fechar", corretamente e inutilmente.

Filtro por filtro:

- **67** — `cursor: pointer` é a evidência: o site está *dizendo ao usuário* que aquilo é
  clicável. Uso `getComputedStyle` (o estilo final, depois de todo o CSS), não o inline.
- **68** — se tem um elemento semântico dentro, o clique é dele. Evita capturar a `div`
  que embrulha um botão.
- **70** — texto acima de 40 caracteres é parágrafo, não botão.
- **73** — sem texto ainda serve, **desde que haja identificador**. É o que faz os cards
  da home do BugBank aparecerem: eles são `<a>` vazios com `id="btn-TRANSFERÊNCIA"`.
- **75–77** — **prefere o elemento mais interno**. Se um filho também parece clicável e
  tem texto, é dele a vez. Sem isso, um container inteiro entraria no lugar do botão.

### O filtro de visibilidade — e o bug do cartão 3D

```javascript
85        const rect = el.getBoundingClientRect();
86        const style = getComputedStyle(el);
87        if (rect.width < 2 || rect.height < 2) return;
88        if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return;
```
Os descartes óbvios: tamanho zero, escondido, transparente.

**Isso não bastou.** Foi o seu relato: *"se eu clico no registrar ele não pega os campos
do registrar"*.

```javascript
90        // Visivel de verdade: o elemento precisa ser o que esta por cima no proprio centro.
95        const cx = rect.left + rect.width / 2;
96        const cy = rect.top + rect.height / 2;
97        if (cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight) {
98          const topo = document.elementFromPoint(cx, cy);
99          if (topo && topo !== el && !el.contains(topo)) return;
100       }
```
**O problema:** o BugBank alterna entre login e cadastro **virando um cartão em 3D**
(`transform: rotateY(180deg)`). Os campos da face escondida continuam com tamanho normal
e `visibility: visible` — eles estão virados de costas, não escondidos. Todo teste de
CSS passa neles.

**A solução:** `document.elementFromPoint(x, y)` pergunta ao navegador *"quem está por
cima neste ponto da tela?"*. Se o que está no centro do elemento não é ele (nem um filho
dele), então há algo na frente — e **não dá para clicar nele**.

É o único teste que separa as duas faces do cartão, porque é o único que pergunta ao
mecanismo de renderização em vez de inferir do CSS.

**De brinde**, isso resolve o caso do modal: com um modal aberto, tudo atrás dele deixa
de ser "o de cima" e sai do inventário automaticamente. O agente passa a enxergar
exatamente o que **você** enxerga.

Resultado medido: o inventário do BugBank foi de **11 elementos misturados das duas
telas** para **5 corretos por tela**.

Linha 97: o teste só se aplica a quem está dentro da viewport — `elementFromPoint`
devolve `null` fora dela, e um elemento fora da tela não deve ser descartado por isso
(basta rolar).

### Rótulo, papel e formulário

```javascript
102       let label = '';
103       if (el.id) {
104         const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
105         if (l) label = first(l.innerText);
106       }
107       if (!label && el.closest('label')) label = first(el.closest('label').innerText);
108       if (!label) label = first(el.getAttribute('aria-label'));
```
As três formas de rotular um campo em HTML, na ordem de preferência: `<label for="...">`,
`<label>` envolvendo o campo, e `aria-label`.

`CSS.escape` protege ids com caracteres especiais — um id como `user.name` quebraria o
seletor sem isso.

> No BugBank **nenhuma** funciona: ele não usa `<label>` nenhum, só `placeholder`. Por
> isso o `placeholder` é peça central aqui, e por isso os nomes que você vê no painel são
> "Informe seu e-mail" em vez de "E-mail".

```javascript
110       const tag = el.tagName.toLowerCase();
111       const isBotao = tag === 'button' || type === 'submit' || type === 'button';
112       let role = el.getAttribute('role') || '';
113       if (!role) {
114         if (isBotao) role = 'button';
115         else if (tag === 'a') role = el.getAttribute('href') ? 'link' : 'button';
119         else if (tag === 'input' || tag === 'textarea') role = 'textbox';
120         else role = 'button';  // div/span clicavel: age como botao
121       }
```
Calcula o **papel ARIA** — o vocabulário que descreve *o que a coisa faz*, e que o
Playwright usa em `get_by_role`. Se o site declarou um, respeitamos; senão, deduzimos.

Linha 115 é sutil e correta: uma âncora **com** href é um `link` (navega); **sem** href
é um `button` (só dispara JavaScript).

```javascript
125       let form = '';
126       const f = el.closest('form');
127       if (f) {
128         const submit = f.querySelector('button[type="submit"]')
129           || f.querySelector('input[type="submit"]')
130           || f.querySelector('button');
131         form = first(submit ? (submit.innerText || submit.value) : '');
132       }
```
**Nomeia o formulário pelo texto do botão de submit dele.** É o que distingue o campo
"e-mail" do login do campo "e-mail" do cadastro: um tem `form: "Acessar"`, o outro
`form: "Cadastrar"`.

`el.closest('form')` sobe a árvore até achar o `<form>` ancestral.

**Por que pelo texto do botão e não pelo `id` ou `name` do form:** porque o texto é
*significado* — "Acessar" e "Cadastrar" querem dizer algo para você e para a LLM.
`form_1` e `form_2` não querem dizer nada. E muitos formulários não têm id nenhum.

```javascript
137       const naoEditaveis = ['checkbox', 'radio', 'file', 'range', 'color'];
138       const editavel = tag === 'textarea'
139         || (tag === 'input' && !isBotao && naoEditaveis.indexOf(type) === -1);
```
**O flag que corrigiu a caixa de busca do Google.**

A busca do Google é uma `<textarea role="combobox">`. Eu classificava pelo papel ARIA, e
`combobox` não é `textbox` — então ela não entrava como campo de texto e o agente "não
achava a barra de pesquisa".

A correção: **classificar pelo tipo do elemento, não pelo papel**. Uma `<textarea>` é um
campo de texto, qualquer que seja o papel que o site declarou. Um `<input>` também é,
exceto os tipos da lista de exclusão.

```javascript
141       const id = 'E' + (++n);
142       el.setAttribute(stamp, id);
```
**O carimbo.** Cada elemento ganha um atributo temporário `data-qai-id="E7"`.

É a chave da **Regra 3**, e o próximo tópico mostra por quê.

```javascript
148         // el.value so serve de rotulo em botao. Em campo de texto, value e o que o
149         // usuario acabou de digitar -- usar isso como nome renomearia o campo
150         // "Informe sua senha" para "Teste@123" depois do primeiro preenchimento.
151         text: first(el.innerText || (isBotao ? el.value : '') || ''),
```
Outro bug real, e daqueles que assustam. Eu usava `el.value` como nome para qualquer
elemento. Em `<input type="submit" value="Enviar">` isso é o rótulo. Mas num campo de
texto, `value` é **o que você acabou de digitar** — então, depois do primeiro `fill`, o
campo "Informe sua senha" aparecia no inventário chamado **"Teste@123"**.

Consequência: o comando seguinte não achava mais o campo, e a sua senha ficava visível
no painel lateral.

O `isBotao ?` no meio da linha limita `value` a botões.

## 8.5 Provar o seletor contra a página viva

Esta seção é a **Regra 3** em funcionamento.

```python
176 def _candidates(raw: dict, *, scoped: bool) -> list[Selector]:
178     form = raw["form"] if scoped else ""
182     out: list[Selector] = []
183     if raw["label"]:
184         out.append(Selector(kind="label", value=raw["label"], form=form))
185     if raw["role"] and raw["text"]:
186         out.append(Selector(kind="role", value=raw["role"], name=raw["text"], form=form))
187     if raw["placeholder"]:
188         out.append(Selector(kind="placeholder", value=raw["placeholder"], form=form))
189     if raw["dom_id"] and not scoped:
190         out.append(Selector(kind="css", value="#" + raw["dom_id"]))
191     if raw["dom_name"]:
192         out.append(Selector(kind="css", value='[name="' + raw["dom_name"] + '"]', form=form))
193     if raw["text"]:
197         out.append(Selector(kind="text", value=raw["text"], form=form))
```
Gera os candidatos **do mais semântico para o mais estrutural**. A ordem é a
recomendação oficial do Playwright, e a razão é manutenção:

| Ordem | Seletor | Por quê |
|---|---|---|
| 1 | `get_by_label` | é como uma pessoa se refere ao campo |
| 2 | `get_by_role` | papel + nome acessível; estável e legível |
| 3 | `get_by_placeholder` | o que funciona no BugBank, que não tem labels |
| 4 | `#id` | estável, mas não diz o que o elemento significa |
| 5 | `[name=...]` | idem |
| 6 | `get_by_text` | último recurso — mas o **único** que acha o "Fechar" do modal |

Um seletor por papel continua funcionando depois de um redesenho de CSS; um seletor
posicional quebra. Por isso a ordem.

### A prova

```python
267     async def _resolves_uniquely(self, selector: Selector, stamp_id: str) -> bool:
268         probe = self.locator(PageElement(element_id=stamp_id, selector=selector))
269         try:
270             if await probe.count() != 1:
271                 return False
272             return await probe.first.get_attribute(STAMP, timeout=1000) == stamp_id
273         except Exception:
274             return False
```
**Quatro linhas que tornam alucinação de seletor impossível.**

O candidato é executado **contra a página real**, e só passa se:

1. **`count() == 1`** — resolve para exatamente **um** elemento. Não zero (não existe),
   não dois (ambíguo).
2. **O carimbo bate** — o elemento encontrado é *aquele mesmo*, e não outro com o mesmo
   texto.

Sem o carimbo, o teste 1 sozinho aceitaria um seletor que acha um elemento único — o
**errado**. O `data-qai-id` é o que amarra a prova.

Nenhum seletor entra no inventário sem passar aqui. Não existe caminho no código em que
um seletor não verificado chegue até uma ação.

```python
276     async def _resolve(self, raw: dict) -> Selector | None:
279         for scoped in (False, True):
280             for candidate in _candidates(raw, scoped=scoped):
281                 if await self._resolves_uniquely(candidate, raw["id"]):
282                     return candidate
```
**Passe 1 e 2.** Primeiro tenta sem escopo. Se todos falharem — tipicamente porque a
página tem dois formulários com campos iguais e todo candidato acha 2 — repete
**ancorando no formulário**, o que corta o espaço pela metade e desempata.

```python
284         # 3. Ultimo recurso: o seletor casa varios, entao fixamos a posicao. Feio, mas
285         # melhor que descartar o elemento -- um elemento fora do inventario e um
286         # elemento que o agente jura nao existir.
287         for candidate in _candidates(raw, scoped=False):
289             total = await self.locator(...).count()
292             for indice in range(min(total, 10)):
293                 posicional = candidate.model_copy(update={"nth": indice})
294                 if await self._resolves_uniquely(posicional, raw["id"]):
295                     return posicional
296         return None
```
**Passe 3 — o feio que é necessário.**

Se nada desempatou, fixamos a posição: `get_by_text("Salvar").nth(2)`. Isso é frágil —
muda a ordem na página e o seletor aponta para outro lugar.

Mas o comentário guarda a lição que eu aprendi errando: **"um elemento fora do inventário
é um elemento que o agente jura não existir"**. Eu tinha removido esse passe enquanto
"simplificava" o código, e elementos começaram a sumir silenciosamente — o agente
respondia "não achei" para coisas visíveis na tela. Um seletor frágil é muito melhor que
um elemento invisível.

`model_copy(update={...})` é o método do Pydantic para copiar um objeto mudando um campo.
`min(total, 10)` limita o esforço.

## 8.6 `snapshot` e as ações

```python
298     async def snapshot(self) -> list[PageElement]:
300         page = await self._ensure_page()
301         raw_elements = await page.evaluate(_COLLECT_JS, STAMP)
303         found: list[PageElement] = []
304         for raw in raw_elements:
305             selector = await self._resolve(raw)
306             if selector is None:
307                 continue
308             found.append(
309                 PageElement(
310                     element_id=raw["id"],
312                     name=(raw["label"] or raw["text"] or raw["placeholder"]
313                           or _nome_do_id(raw["dom_id"]) or raw["dom_name"]),
...
321         self.elements = found
```
**`page.evaluate(js, arg)`** executa JavaScript dentro da página e traz o resultado de
volta para o Python, convertido automaticamente (array JS → lista Python, objeto →
dict). É a ponte entre os dois mundos.

Linhas 312–313: o **nome** é a primeira coisa não-vazia desta lista de prioridade:
`label` → `text` → `placeholder` → nome derivado do id → `name`.

```python
165 def _nome_do_id(dom_id: str) -> str:
172     limpo = re.sub(r"^(?:btn|button)[-_]?", "", dom_id or "", flags=re.IGNORECASE)
173     return re.sub(r"[-_]+", " ", limpo).strip()
```
`"btn-TRANSFERÊNCIA"` → `"TRANSFERÊNCIA"`. Remove o prefixo técnico e troca separadores
por espaço.

Sem isso, os cards da home do BugBank entravam no inventário **sem nome nenhum**, e a LLM
não tinha como escolher entre eles.

```python
326     async def goto(self, url: str) -> None:
327         page = await self._ensure_page()
328         await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
329         await self._settle()  # SPA terminar de montar
```
`wait_until="domcontentloaded"` espera o HTML ser interpretado, **não** todas as imagens
e scripts (`load`). Numa SPA, `load` pode nunca acontecer de forma útil, e o conteúdo que
importa é montado por JavaScript depois — é o `_settle()` que cuida disso.

```python
331     async def fill(self, element: PageElement, value: str) -> None:
332         await self.locator(element).fill(value, timeout=15_000)
333         await self._settle()
339     async def click(self, element: PageElement) -> None:
340         await self.locator(element).click(timeout=15_000)
341         await self._settle()
```
O padrão: **agir, depois esperar a página assentar**.

`.fill()` do Playwright faz mais do que parece: espera o elemento existir, estar visível e
habilitado, foca, limpa o conteúdo anterior e digita, disparando os eventos que frameworks
como o React escutam. Um `value = "x"` direto no DOM não funcionaria — o React não veria.

`.click()` da mesma forma: espera o elemento estar **acionável** (visível, estável, sem
nada na frente) antes de clicar. É isso que gera a mensagem `intercepts pointer events`
quando há um modal aberto — o Playwright se recusa a clicar em algo que você não
conseguiria clicar.

```python
349     async def has_text(self, text: str) -> bool:
355         page = await self._ensure_page()
358         padrao = to_pattern(text)
359         alvo = padrao if padrao is not None else text
360         try:
361             await page.get_by_text(alvo).first.wait_for(state="visible", timeout=10_000)
362             return True
363         except Exception:  # noqa: BLE001 - nao achar o texto e um resultado, nao um erro
364             return False
```
A validação. Três coisas importantes:

1. **`get_by_text` normaliza espaços em branco.** A mensagem de erro do BugBank é quebrada
   em várias linhas no HTML; uma comparação literal falharia. O Playwright trata isso.
2. **Aceita string ou regex.** É por isso que a máscara funciona: passamos o `re.Pattern`
   no lugar do texto e o resto do caminho é idêntico.
3. **`wait_for(state="visible", timeout=10_000)`** — espera até 10s. Mensagens de erro
   costumam aparecer com animação; falhar imediatamente daria falso negativo.

O comentário da linha 363 é a parte conceitual: **não achar o texto é um resultado, não um
erro**. Retornamos `False`, o nó `validar_texto` transforma em bolha vermelha, e isso é
um teste que falhou — possivelmente o bug que você está caçando.

```python
366     async def screenshot(self) -> bytes | None:
368         if not self.is_open:
369             return None
370         try:
371             return await self._page.screenshot(type="jpeg", quality=55, timeout=5_000)
372         except Exception:  # noqa: BLE001 - durante navegacao a captura falha; o chat
373             return None    # simplesmente mantem o quadro anterior
```
`type="jpeg", quality=55` — JPEG e não PNG porque a imagem vai pela rede **3 vezes por
segundo**. Um PNG de 1280×800 tem centenas de KB; um JPEG a 55% tem algumas dezenas.
Qualidade 55 é feia para uma foto e perfeitamente legível para uma tela de aplicação.

Retornar `None` durante uma navegação (o contexto morreu, a captura falha) é o
comportamento certo: o chat mantém o quadro anterior em vez de piscar.

---

# Parte 9 — A resposta volta para a tela

O caminho de volta, em ordem:

1. **`run_action`** (ou `run_expect_text`) devolve um `CommandResult`, e o nó o embrulha
   em `{"result": ...}`;
2. **O LangGraph** mescla no estado e vai para `END`;
3. **`graph.ainvoke`** retorna o estado final (`server.py:124`);
4. **Deu certo?** `gravacao.registrar(final, url_antes)` anota o passo — é aqui que o
   teste salvo é construído, um comando de cada vez (Parte 13);
5. **`_reply()`** converte para `Reply`, acrescentando URL e inventário atuais;
6. **O FastAPI** serializa a lista em JSON (o Pydantic faz isso sozinho);
7. **O `fetch`** no navegador recebe;
8. **`mostrarPassos()`** desenha uma bolha por passo;
9. **`atualizar()`** sincroniza cabeçalho e painel lateral;
10. **`atualizarGravacao()`** relê o painel de gravação, no `finally`.

E o `/api/tela`, em paralelo, já está mostrando o resultado visual — normalmente **antes**
da bolha aparecer, porque o polling é mais rápido que o ciclo do comando.

---

# Parte 10 — Vários comandos numa mensagem só (`commands.py`)

Esta parte nasceu do seu relato: *"ele não faz duas ações ao mesmo tempo"*.

## 10.1 Por que a divisão é determinística

A tentação seria mandar a frase inteira para a LLM e pedir a lista de ações. **Isso é
exatamente o cenário em que o qwen3:1.7b degenera** — foi o segundo experimento da minha
tabela: repetiu `click` em loop e perdeu os `fill`.

Separando aqui, **antes** de qualquer LLM, cada pedaço volta a ser a pergunta pequena que
ele acerta. **Regra 1**, aplicada de novo.

## 10.2 O padrão

```python
25  _VERBS = (
26      r"(?:cli(?:c|qu)\w*|verifi(?:c|qu)\w*|mar(?:c|qu)\w*|colo(?:c|qu)\w*|"
27      r"aperte|apertar|pression\w*|preench\w*|digit\w*|escrev\w*|"
28      r"inform\w*|insir\w*|inser\w*|valid\w*|confir\w*|acess\w*|abr\w*|"
29      r"localiz\w*|encontr\w*|selecion\w*|navegue|navegar|v[aá]\s)"
30  )
```
Os verbos que **iniciam uma ordem nova**.

O comentário acima deles guarda um bug que custou caro:

```python
22  # Atencao ao radical: em portugues varios desses verbos alternam c/qu entre as
23  # formas (clicar / clique, verificar / verifique), entao o padrao precisa aceitar os
24  # dois -- "clic\w*" sozinho nao casa com "clique".
```

`clicar` → `clic` + `ar`. `clique` → `cliqu` + `e`. **O radical muda.** Eu tinha escrito
`clic\w*`, que casa com "clicar" e "clicando" mas **não** com "clique" — a forma que
todo mundo usa no imperativo. Metade dos comandos não era dividida, e ninguém via porquê.

`v[aá]\s` no fim cobre "vá para" com e sem acento, exigindo um espaço depois para não
casar com qualquer palavra que comece com "va".

```python
33  _SPLIT_RE = re.compile(
34      r"(?:[,;]\s*(?:e\s+)?|\s+e\s+)"
35      r"(?:logo\s+)?(?:em\s+seguida\s*,?\s*|depois\s*,?\s*|ent[aã]o\s*,?\s*)?"
36      r"(?=" + _VERBS + r")",
37      re.IGNORECASE,
38  )
```
Três partes:

- **34** — o conector: vírgula/ponto-e-vírgula (com "e" opcional depois), ou " e ".
- **35** — advérbios opcionais: "logo em seguida", "depois", "então".
- **36** — **`(?=...)`, um lookahead positivo.** Ele exige que o que vem a seguir seja um
  verbo, mas **não consome** o texto — o verbo continua fazendo parte do próximo comando.

**O lookahead é a trava contra cortes errados.** Sem ele, `"informe o nome João e Maria"`
seria cortado no " e ", destruindo um valor. Com ele, só corta se depois vier um verbo de
ação — e "Maria" não é verbo.

## 10.3 Proteger o texto entre aspas

```python
44  def _mask(text: str) -> tuple[str, list[str]]:
45      guardados: list[str] = []
47      def troca(match: re.Match) -> str:
48          guardados.append(match.group(0))
49          return _PLACEHOLDER.format(len(guardados) - 1)
51      return _QUOTED_RE.sub(troca, text), guardados
```
**O problema:** a mensagem de erro do BugBank é
`"Usuário ou senha inválido. Tente novamente ou verifique suas informações!"`.

Ela contém a palavra **"verifique"** — um verbo de ação. Sem proteção, o divisor cortaria
**dentro da mensagem esperada**, e a validação compararia contra meia frase.

**A solução:** antes de dividir, cada trecho entre aspas é substituído por um marcador
(`\x00 0 \x00`), e depois restaurado. O divisor nunca vê o conteúdo das aspas.

`\x00` (byte nulo) como marcador é escolha deliberada: é um caractere que **não pode**
aparecer num texto digitado, então não há risco de colisão.

`re.sub` aceitando uma **função** em vez de string é o que permite guardar o original e
devolver um marcador diferente a cada ocorrência.

```python
60  def split_commands(text: str) -> list[str]:
62      mascarado, guardados = _mask(text)
63      pedacos = [
64          _unmask(pedaco, guardados).strip(" ,;.")
65          for pedaco in _SPLIT_RE.split(mascarado)
66      ]
67      limpos = [pedaco for pedaco in pedacos if pedaco]
68      return limpos or [text.strip()]
```
Mascara → divide → restaura → limpa pontuação das pontas → descarta vazios.

Linha 68: `limpos or [text.strip()]` — se sobrou nada, devolve o texto original inteiro.
**Nunca devolve lista vazia**, porque quem chama itera sem checar.

**Verificação:** a bateria de testes de divisão passa **7/7**, incluindo o caso do cenário
completo com a mensagem entre aspas contendo "verifique".

---

# Parte 11 — A tela ao vivo

Você pediu: *"tem como a gente deixar a tela do Chrome na mesma página que estamos
digitando o chat?"*. Isto é a resposta.

```javascript
386 const tela = document.getElementById('tela');
389 let transmitindo = false;
391 async function quadro() {
392   if (transmitindo) return;
393   transmitindo = true;
```
**A trava `transmitindo` é o detalhe que faz funcionar.**

O `setInterval` dispara a cada 350ms independentemente de a requisição anterior ter
voltado. Se o browser estiver lento e um quadro demorar 2 segundos, sem essa trava você
acumularia 6 requisições concorrentes, cada uma pedindo um screenshot — e o Playwright
ficaria mais lento ainda, num círculo vicioso.

Com ela: **nunca há mais de uma requisição em voo**. Se o quadro demora, a taxa cai
sozinha. É controle de fluxo em três linhas.

```javascript
395     const resposta = await fetch('/api/tela?t=' + Date.now());
396     if (resposta.status === 204) {
397       aviso.hidden = false;
398       selo.hidden = true;
399       tela.removeAttribute('src');
```
`?t=` + timestamp faz cada URL ser única — a segunda trava contra cache (a primeira é o
`Cache-Control: no-store` do servidor).

O 204 significa "sem browser": mostra o aviso, esconde o selo "ao vivo", limpa a imagem.

```javascript
401       const blob = await resposta.blob();
402       const anterior = tela.src;
403       tela.src = URL.createObjectURL(blob);
404       if (anterior.startsWith('blob:')) URL.revokeObjectURL(anterior);
```
**`blob()`** pega o corpo como dado binário. **`URL.createObjectURL(blob)`** cria uma URL
local (`blob:http://...`) que aponta para esse dado na memória do navegador.

**A linha 404 é obrigatória, não opcional.** Cada `createObjectURL` reserva memória que
**só** é liberada quando você chama `revokeObjectURL`. A 3 quadros por segundo, esquecer
isso vaza uns 100KB/s — em dez minutos são centenas de megabytes e a aba trava.

A ordem importa: guardo a URL anterior, defino a nova, **só então** revogo a antiga. Ao
contrário, haveria um instante com a imagem apontando para dados liberados, e ela
piscaria.

```javascript
408   } catch (e) {
409     // servidor caiu ou reiniciou: mantem o ultimo quadro e tenta de novo
410   } finally {
411     transmitindo = false;
412   }
415 setInterval(quadro, 350);
```
O `catch` vazio é intencional e está documentado: se o servidor reiniciou, a melhor coisa
a fazer é **nada** — manter o último quadro e tentar de novo em 350ms. Encher o chat de
erros de rede seria pior.

O `finally` garante que a trava é liberada mesmo em erro. Sem ele, um único erro de rede
congelaria a transmissão para sempre.

**Por que 350ms e não 60fps:** cada quadro é um screenshot real do Chromium, que custa
CPU. 350ms (≈3 fps) é suficiente para acompanhar o agente agindo e deixa a máquina livre
para o que importa. Não é vídeo, é acompanhamento.

```javascript
417 montarChips();
418 bolha('Para qual URL você quer ir?', 'bot');
419 fetch('/api/estado').then(r => r.json()).then(atualizar);
420 atualizarGravacao();
421 atualizarTestes();
422 quadro();
```
A inicialização. Linha 422 pede o primeiro quadro **imediatamente**, sem esperar os
350ms — se você recarregou a página com o browser já aberto, a tela aparece na hora.

Linhas 420–421 fazem o mesmo pela gravação e pela lista de testes, e pelo mesmo motivo do
`/api/estado`: **quem guarda a verdade é o servidor**. Você pode dar F5 no meio de um
cenário que os passos já gravados continuam lá.

---

# Parte 12 — Os arquivos de apoio

## 12.1 `models.py`

```python
11  class Action(str, Enum):
12      GOTO = "goto"
...
19      @property
20      def needs_element(self) -> bool:
21          return self in (Action.FILL, Action.CLICK, Action.LOCATE, Action.CLEAR)
```
Herdar de **`str` e `Enum`** ao mesmo tempo é um truque útil: `Action.CLICK` se comporta
como a string `"click"` onde se espera uma string, mas continua sendo um enum com
autocomplete e verificação.

`needs_element` mora **no enum**, não espalhado em `if`s pelo grafo. Uma ação nova declara
sozinha se precisa de elemento. É o tipo de coisa que evita bug seis meses depois.

```python
34  class Selector(BaseModel):
38      kind: Literal["placeholder", "label", "role", "css", "text"]
39      value: str
40      name: str = ""  # so para kind="role": o nome acessivel
41      form: str = ""  # escopo opcional no formulario, pelo texto do botao de submit
42      nth: int | None = None  # ultimo recurso: fixa a posicao quando nada mais desempata
```
**Por que o seletor é um objeto estruturado e não uma string.**

Se eu guardasse `'page.get_by_placeholder("E-mail")'` como texto, para executar eu teria
que interpretar essa string de volta — ou pior, usar `eval`. Guardando estruturado, o
mesmo objeto gera **duas** coisas diferentes:

- `browser.locator()` → um Locator de verdade, para agir;
- `to_code()` → o trecho de código Python, para você ler e copiar.

`Literal[...]` restringe `kind` a esses cinco valores; o Pydantic recusa qualquer outro.

```python
44      def to_code(self) -> str:
45          return self._expr() if self.nth is None else f"{self._expr()}.nth({self.nth})"
47      def _expr(self) -> str:
48          base = f'page.locator(\'form:has(button:text-is("{self.form}"))\')' if self.form else "page"
49          if self.kind == "placeholder":
50              return f"{base}.get_by_placeholder({self.value!r}, exact=True)"
```
Gera o código legível. O `form:has(button:text-is("Acessar"))` é sintaxe do Playwright:
*"o `<form>` que contém um `<button>` cujo texto é exatamente 'Acessar'"*. É assim que o
escopo por formulário vira um seletor de verdade.

`{self.value!r}` de novo: `repr()` para produzir um literal Python colável.

```python
60  class PageElement(BaseModel):
71      def describe(self) -> str:
72          bits = [self.role or "elemento"]
73          if self.name:
74              bits.append(f'"{self.name}"')
75          if self.form:
76              bits.append(f"[{self.form}]")
77          return " ".join(bits)
```
`describe()` produz `textbox "Informe seu e-mail" [Acessar]` — o formato que vai para o
prompt da LLM **e** para o painel lateral.

**Usar o mesmo texto nos dois lugares é deliberado:** o que você vê no painel é
*exatamente* o que a LLM vê. Quando ela erra, você consegue olhar e entender por quê.

### `Step` — um comando depois que a LLM já trabalhou

```python
90  class Step(BaseModel):
97      action: Action
98      text: str = ""          # o comando original, so para leitura humana
99      value: str = ""
100     selector: Optional[Selector] = None
101     element_name: str = ""
102     element_form: str = ""
105     code: str = ""
```
O que sobra de um comando quando a interpretação já aconteceu: a ação escolhida, o
seletor verificado, o valor recortado. É a unidade do teste salvo.

Campo a campo, e o porquê de cada um:

| Campo | Para quê |
|---|---|
| `action` | o que fazer |
| `selector` | **onde** — estruturado, o mesmo objeto que vira Locator |
| `value` | o dado (URL, e-mail, senha, texto esperado) |
| `element_name` / `element_form` | para a mensagem ("Preenchi \"E-mail\"") e para o rótulo no painel |
| `text` | o comando que você digitou; não é usado para executar |
| `code` | o trecho Playwright que **de fato rodou** |

Duas escolhas que merecem explicação.

**Por que `text` é guardado se não é usado.** Para você abrir o `.json` seis meses depois
e entender o teste sem decifrar seletor. É documentação dentro do dado — e, se um dia o
teste precisar ser regravado, é o roteiro de volta.

**Por que `code` existe se o `selector` já gera código.** Porque uma validação de texto
**não tem elemento**: o "seletor" dela é um matcher (`expect(page.get_by_text(...))`)
montado na hora, às vezes com regex de máscara. Sem guardar o código executado, o passo
de validação apareceria sem código nenhum no arquivo.

```python
107     @property
108     def selector_code(self) -> str:
109         if self.code:
110             return self.code
111         return self.selector.to_code() if self.selector else ""
119     def to_element(self) -> Optional[PageElement]:
121         if self.selector is None:
122             return None
123         return PageElement(
124             element_id="gravado",
125             name=self.element_name,
126             form=self.element_form,
127             selector=self.selector,
128         )
```
`selector_code` prefere o código gravado e cai no seletor como reserva — assim um arquivo
antigo, sem o campo `code`, continua mostrando algo útil.

`to_element` remonta o `PageElement` que o `browser.locator()` espera. Ele é
**sintético**: `element_id="gravado"` em vez de um carimbo real (`E7`), porque aquele
carimbo pertencia a uma página que já não existe. Nada na execução usa esse id — só o
`selector` importa — e o valor deixa claro na depuração de onde o elemento veio.

### `TestCase` — o arquivo inteiro

```python
131 class TestCase(BaseModel):
134     name: str
135     slug: str
136     created_at: str
139     url_inicial: str = ""
140     steps: list[Step] = []
```
`model_dump_json()` transforma isso no arquivo e `model_validate_json()` traz de volta,
**validando**. É a razão de o formato ser Pydantic e não um `dict` solto: um `.json`
editado à mão com um campo errado é recusado na leitura, em vez de explodir no meio da
execução do teste.

## 12.2 `textutil.py`

```python
 8  def normalize(text: str) -> str:
 9      decomposed = unicodedata.normalize("NFKD", (text or "").lower())
10      return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()
```
**Remove acentos.** O mecanismo: `NFKD` é uma forma de normalização Unicode que
**decompõe** cada caractere acentuado em letra base + marca de acento separada — `"ç"`
vira `"c"` + cedilha. Depois, `unicodedata.combining(ch)` identifica as marcas, e o
filtro joga fora.

**Por que é indispensável:** você escreve "transferencia" sem acento, a página tem
"TRANSFERÊNCIA". Sem normalizar, nada casa. E em português isso acontece o tempo todo.

```python
13  def tokens(text: str) -> set[str]:
14      cleaned = "".join(ch if ch.isalnum() else " " for ch in normalize(text))
15      return {token for token in cleaned.split() if len(token) > 2}
```
Transforma texto num **conjunto** de palavras comparáveis: normaliza, troca pontuação por
espaço e descarta palavras de até 2 letras.

O corte em 2 letras remove "de", "do", "da", "no", "em" — palavras que aparecem em
qualquer frase e casariam com tudo, inflando a pontuação de `_fuzzy` e enfraquecendo o
`_plausible`.

Retornar `set` é o que permite `tokens(a) & tokens(b)` — interseção, usada em
`_plausible` e `_fuzzy`.

## 12.3 `.env.example` e `requirements.txt`

O `.env.example` é o modelo comentado; você copia para `.env` e ajusta. O `.env` real
está no `.gitignore` — **chave de API nunca vai para o repositório**.

O `requirements.txt` fixa versões mínimas por grupo: LangChain/LangGraph/LangSmith,
Playwright, FastAPI/uvicorn, Pydantic.

---

# Parte 13 — Gravar e reexecutar um teste (`suite.py`)

Até aqui o documento seguiu **um comando**, do teclado ao clique. Esta parte é sobre o
que acontece depois dele: o passo que deu certo vira linha de um teste, e o teste vira um
arquivo que roda sozinho.

É também a única parte do projeto em que o agente **não pensa** — e isso é o ponto.

## 13.1 A ideia: o que sobra quando a LLM já decidiu

Um comando interpretado custa duas chamadas de LLM local, mais o Playwright. Rodar um
cenário de cinco passos custa dez chamadas. A pergunta que dá origem a esta parte é:
**preciso pagar isso de novo para repetir exatamente o mesmo fluxo?**

Olhe o que existe dentro de `"informe o e-mail qualquerCoisa0001@gmail.com"` depois que
o grafo terminou:

- **a decisão** — a ação é `fill`, o elemento é aquele campo, com *este* seletor;
- **a execução** — chamar `.fill()` naquele locator.

A decisão é a parte cara e incerta. A execução é barata e determinística. **Gravar um
teste é congelar a decisão e guardar só a execução.**

| | Conversando | Rodando um teste salvo |
|---|---|---|
| Quem escolhe o elemento | a LLM, conferida contra a página | ninguém: está no arquivo |
| Chamadas ao Ollama | 2 por comando | **zero** |
| Como acha o elemento | lê o DOM, monta candidatos, prova cada um | aplica o seletor gravado |
| Se a página mudar | o agente se vira | o passo falha |

A última linha é o preço, e é honesto pagá-lo: um teste **deve** falhar quando a tela
muda. É para isso que ele existe.

> **Por que isto é confiável, e não uma aposta.** Vale a Regra 3 (seletor nunca é
> inventado). O seletor que está no arquivo não é o palpite da LLM: é o candidato que
> passou pela prova da Parte 8.5 — foi testado contra o DOM vivo e resolveu, sozinho,
> exatamente aquele elemento. Congelar um palpite seria péssima ideia; congelar uma
> prova é o que faz a reexecução funcionar.

## 13.2 `Gravacao` — anotar o que deu certo

```python
37  class Gravacao:
40      def __init__(self) -> None:
41          self.steps: list[Step] = []
42          self.url_inicial: str = ""
```
Uma lista e uma string, e nada mais. Ela vive no `server.py` como um objeto só, ao lado da
`session` — a gravação é da sessão, não de uma requisição.

```python
44      def registrar(self, state: dict, url_antes: str) -> None:
51          action = state.get("action")
52          if action is None:
53              return
55          element = state.get("element")
56          resultado = state.get("result")
57          if not self.steps:
58              self.url_inicial = url_antes
```
O parâmetro é o **estado final do grafo** — aquele mesmo dicionário que o `ainvoke`
devolveu. Não há nada a recalcular: `action`, `element` e `value` já estão ali, decididos
e usados. Gravar é copiar.

**Linhas 57–58: a URL de partida, uma vez só.** Ela é anotada quando o *primeiro* passo
entra, e com o valor de **antes** de o passo rodar. As duas coisas importam: se fosse
lida depois, um clique que navega já teria trocado a página; se fosse atualizada a cada
passo, acabaria guardando a última tela do fluxo em vez da primeira.

```python
60          self.steps.append(Step(
61              action=action,
62              text=state.get("text", ""),
63              value=state.get("value") or "",
64              selector=element.selector if element else None,
65              element_name=element.name if element else "",
66              element_form=element.form if element else "",
67              code=resultado.selector_code if resultado else "",
68          ))
```
O `if element else` repetido não é descuido: `goto` e `expect_text` agem na página
inteira e chegam aqui **sem elemento**. O `Step` aceita isso (`selector` é opcional) e a
execução sabe lidar.

`state.get("value") or ""` cobre dois casos com um operador: a chave ausente e o valor
`None` de um comando que não tinha dado nenhum (um clique). `Step.value` é `str`, e o
Pydantic recusaria `None`.

**Quem decide o que é gravado não está aqui.** É o `server.py` (linha 131) que só chama
`registrar` quando `resultado.ok`. A separação é de propósito: a `Gravacao` anota o que
mandarem; a regra de negócio — *passo que falhou não é passo* — fica onde a resposta é
montada.

## 13.3 O arquivo: salvar, carregar, listar

```python
28  def _slug(nome: str) -> str:
29      limpo = re.sub(r"[^a-z0-9]+", "-", normalize(nome)).strip("-")
30      return limpo or "teste"
```
`"Login inválido"` → `"login-invalido"`. O `normalize` (Parte 12.2) já tira acento e
maiúscula; a regex troca todo o resto por hífen. O `or "teste"` cobre um nome que vire
string vazia — alguém digitando só emoji não deve gerar um arquivo chamado `.json`.

```python
77  def salvar(nome: str, gravacao: Gravacao) -> TestCase:
79      if not gravacao.steps:
80          raise ValueError("Nada gravado ainda — rode os comandos no chat antes de salvar.")
82      caso = TestCase(
83          name=nome.strip() or "teste",
84          slug=_slug(nome),
85          created_at=datetime.now().isoformat(timespec="seconds"),
86          url_inicial=gravacao.url_inicial,
87          steps=list(gravacao.steps),
88      )
89      PASTA.mkdir(parents=True, exist_ok=True)
90      _caminho(caso.slug).write_text(caso.model_dump_json(indent=2), encoding="utf-8")
```
Quatro detalhes:

- **`raise ValueError` e não retornar um erro.** Salvar nada é um pedido inválido, não um
  resultado. Quem chama (`server.py:181`) captura e devolve a mensagem no chat.
- **`list(gravacao.steps)`** copia. Sem o `list()`, o `TestCase` guardaria a *mesma* lista
  que a gravação continua usando — e um comando novo depois de salvar entraria num teste
  que já estava no disco.
- **`mkdir(exist_ok=True)`** cria `testes/` na primeira vez. Não é preciso versionar uma
  pasta vazia só para o programa funcionar.
- **`indent=2`** gasta bytes de propósito: o arquivo é para ser **lido**. É nele que você
  confere qual seletor o agente escolheu.

Nome repetido **sobrescreve**, e isso é a funcionalidade de regravar: refaça o fluxo no
chat, salve com o mesmo nome, o arquivo é substituído.

```python
104 def listar() -> list[TestCase]:
108     for arquivo in sorted(PASTA.glob("*.json")):
109         try:
110             casos.append(TestCase.model_validate_json(arquivo.read_text(encoding="utf-8")))
111         except Exception:
112             continue
```
O `try` por arquivo é o que mantém a lista de pé. Estes arquivos são editáveis à mão —
é uma vantagem — e um deles quebrado não pode sumir com todos os outros da tela.

E o arquivo, de verdade — um passo do `testes/login-invalido.json`:

```json
{
  "action": "fill",
  "text": "informe o e-mail qualquerCoisa0001@gmail.com",
  "value": "qualquerCoisa0001@gmail.com",
  "selector": {
    "kind": "placeholder",
    "value": "Informe seu e-mail",
    "name": "",
    "form": "Acessar",
    "nth": null
  },
  "element_name": "Informe seu e-mail",
  "element_form": "Acessar",
  "code": "page.locator('form:has(button:text-is(\"Acessar\"))').get_by_placeholder('Informe seu e-mail', exact=True)"
}
```

Repare que o `form: "Acessar"` sobreviveu. Aquele desempate entre o e-mail do login e o
do cadastro (Parte 6.7), que a LLM e o `disambiguate` resolveram uma vez, está gravado —
na reexecução ele não precisa ser resolvido de novo.

## 13.4 `rodar` — a reexecução

```python
118 async def rodar(session: BrowserSession, caso: TestCase) -> list[tuple[str, CommandResult]]:
125     saida: list[tuple[str, CommandResult]] = []
126     total = len(caso.steps)
128     session.active_form = ""
129     session.last_element = None
```
Zerar `active_form` e `last_element` antes de começar: o teste não pode herdar o contexto
da conversa que você estava tendo. Ele começa do zero, como começará amanhã no CI.

```python
131     # Se o teste nao comeca abrindo a pagina, abrimos por ele.
132     comeca_abrindo = bool(caso.steps) and caso.steps[0].action == Action.GOTO
133     if caso.url_inicial and not comeca_abrindo:
134         abertura = await run_action(session, Action.GOTO, None, caso.url_inicial)
135         saida.append((f"preparando: {caso.url_inicial}", abertura))
136         if not abertura.ok:
137             return saida
```
**Para que serve o `url_inicial`.** Nem todo teste começa com "abra o site" — você pode
ter navegado antes e só depois começado a gravar. Sem isto, o primeiro seletor do teste
procuraria numa página em branco, ou pior, na página em que você estivesse por acaso.

O passo de abertura entra na saída com o rótulo `preparando:`, e não numerado — ele não é
um passo do seu teste, é o palco sendo montado. Se ele falhar, não faz sentido continuar.

```python
139     for indice, step in enumerate(caso.steps):
140         if step.action == Action.EXPECT_TEXT:
141             resultado = await run_expect_text(session, step.value)
142         else:
143             resultado = await run_action(session, step.action, step.to_element(), step.value)
145         saida.append((f"{indice + 1}/{total}: {step.label}", resultado))
```
**O laço inteiro do "agente" reexecutando é isto.** Cinco linhas, e nenhuma delas fala com
a LLM. O `if` separa as duas portas do `actions.py` (Parte 5.7), e o `to_element()`
remonta o `PageElement` a partir do seletor gravado (Parte 12.1).

O rótulo `"3/5: clicar: Acessar"` é montado aqui e vai para o campo `step` do `Reply` — o
mesmo campo que o chat usa para "2/4". Por isso a bolha sai idêntica.

```python
147         if not resultado.ok:
148             restantes = total - indice - 1
149             if restantes:
150                 saida.append(("", CommandResult(
151                     ok=False,
152                     message=f"Parei aqui — {restantes} passo(s) seguinte(s) nao foram executados.",
153                 )))
154             break
```
Mesma regra do chat (Parte 2.2), mesma razão: depois de um preenchimento que não
aconteceu, o clique seguinte só produziria um segundo erro, e você teria que descobrir
qual é a causa e qual é a consequência.

**Por que devolver tuplas `(rótulo, resultado)`** em vez de já montar o `Reply`: o
`suite.py` não conhece o servidor. Ele trabalha com os tipos do agente; quem traduz para
o contrato HTTP é o `server.py`, num lugar só. O mesmo `rodar` serve a uma futura linha
de comando sem mudar uma vírgula.

## 13.5 O painel, no navegador

Três funções e dois botões, em `index.html`. Nenhuma delas desenha bolha nova: o replay
reaproveita o `mostrarPassos` do chat (Parte 4.1).

```javascript
294 async function atualizarGravacao() {
296     const dados = await (await fetch('/api/gravacao')).json();
305       const texto = document.createElement('span');
306       texto.textContent = passo.label;
308       li.title = passo.selector_code || '';
```
Desenha `1. preencher: Informe seu e-mail`. **A linha 308 é a que importa para você
confiar no que está gravando**: o seletor inteiro fica no `title`, então passar o mouse
mostra exatamente o código que aquele passo vai executar. O painel não é um resumo
bonitinho — é a prova, ao alcance do cursor.

```javascript
339 async function rodarTeste(teste) {
340   bolha('Rodar o teste "' + teste.nome + '"', 'user');
341   enviar.disabled = true;
350     const passos = await resposta.json();
352     mostrarPassos(passos);
353     const falhou = passos.some((passo) => !passo.ok);
354     bolha(falhou ? 'Teste reprovado.' : 'Teste aprovado — todos os passos passaram.',
355           'bot', falhou ? 'fail' : 'ok');
```
Rodar um teste aparece no chat **como se você tivesse digitado** — bolha sua na direita,
passos do agente na esquerda. Não é enfeite: mantém um histórico só, na ordem em que as
coisas aconteceram, quando você alterna entre conversar e reexecutar.

A linha 353 é o veredito. Cada passo já tem seu verde ou vermelho; esta bolha final
responde a pergunta que interessa depois de cinco passos — **passou ou não?**

`enviar.disabled = true` na linha 341 pelo mesmo motivo do chat: um browser só, uma ação
por vez. Disparar um comando no meio de um teste bagunçaria os dois.

```javascript
364 document.getElementById('salvarTeste').onclick = async () => {
365   const nome = nomeTeste.value.trim();
366   if (!nome) { nomeTeste.focus(); return; }
373   bolha(dados.message, 'bot', dados.ok ? 'ok' : 'fail');
374   if (dados.ok) nomeTeste.value = '';
375   atualizarTestes();
```
Sem nome, o foco volta para o campo em vez de aparecer um alerta. O resultado — inclusive
"Nada gravado ainda" — vira bolha no chat, porque é lá que você está olhando.

## 13.6 O que esta parte **não** faz

Honestidade sobre os limites, que são escolhas e não esquecimentos:

- **O teste não se adapta.** Mudou o placeholder do campo, o passo falha. É o
  comportamento certo para um teste, e é o oposto do que o chat faz.
- **A gravação vive no processo.** Se o servidor reiniciar antes de você salvar, os
  passos se perdem. Salvar é o que os torna permanentes.
- **Não há botão de apagar.** Apagar arquivo é irreversível e não estava no pedido;
  hoje é `del testes\<nome>.json`. Salvar com o mesmo nome regrava.
- **Um teste por vez, um browser por vez.** Mesma limitação da sessão (Parte 2.2): isto
  é um agente local, de um usuário só.
- **Não gera arquivo `.py`.** O código Playwright de cada passo está no JSON e na bolha,
  pronto para copiar, mas montar um `test_*.py` executável por `pytest` é outro passo —
  e é o caminho natural se um dia isto precisar rodar em CI.

---

# Como rodar

```powershell
# uma vez
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

# sempre
python -m qai
```

Depois abra `http://127.0.0.1:8000` no Chrome.

**Pré-requisito:** o Ollama precisa estar rodando com o `qwen3:1.7b` baixado. O
`health_check` confere isso e te diz o comando exato se faltar.

Os testes salvos ficam em `testes/*.json` e são criados sozinhos na primeira vez que você
clica em **Salvar**. Reexecutar um deles **não** precisa do Ollama — só do browser.

---

# Glossário

| Termo | O que significa aqui |
|---|---|
| **LLM** | *Large Language Model*. O `qwen3:1.7b` rodando na sua máquina via Ollama. |
| **Agente** | LLM que percebe um ambiente, decide e age por ferramentas, em ciclo. |
| **Ollama** | Programa que roda LLMs localmente e as expõe numa API HTTP. |
| **LangChain** | Biblioteca que dá uma interface comum a diferentes LLMs. Aqui: `ChatOllama` e os tipos de mensagem. |
| **LangGraph** | Biblioteca para descrever fluxos como máquina de estados. Aqui: o ciclo de um comando. |
| **LangSmith** | Painel web onde cada chamada de LLM vira um registro inspecionável. |
| **Prompt** | O texto enviado à LLM. Divide-se em *system* (instrução) e *user* (a pergunta). |
| **Few-shot** | Ensinar por exemplos dentro do prompt, fingindo uma conversa anterior. |
| **Temperatura** | Quanto a LLM sorteia. 0 = sempre a saída mais provável. |
| **Token** | O pedaço de texto que a LLM processa. ~4 caracteres em média. |
| **Janela de contexto** | Quantos tokens a LLM enxerga de uma vez (`num_ctx`). |
| **JSON Schema** | Descrição formal de um formato JSON. Aqui, a trava da saída. |
| **Decodificação restrita** | Impedir a LLM de gerar tokens fora do schema. Torna saída inválida impossível. |
| **Enum** | Lista fechada de valores permitidos. |
| **Alucinação** | Quando a LLM inventa algo plausível e falso. |
| **Playwright** | Biblioteca de automação de browser. |
| **Locator** | Objeto do Playwright que representa "como achar um elemento". Preguiçoso: só busca quando usado. |
| **Seletor** | A regra de busca em si (placeholder, papel, CSS…). |
| **DOM** | A árvore de elementos da página, como o navegador a mantém em memória. |
| **SPA** | *Single Page Application*. O HTML vem quase vazio e o JavaScript monta tudo. O BugBank é uma. |
| **Papel ARIA** | Vocabulário que descreve o que um elemento faz (`button`, `textbox`). |
| **MutationObserver** | API do navegador que avisa quando o DOM muda. |
| **Headless** | Browser rodando sem janela visível. |
| **Viewport** | A área visível da página. |
| **FastAPI** | Framework web assíncrono em Python. |
| **Uvicorn** | O servidor que efetivamente fala HTTP. |
| **Pydantic** | Validação de dados por anotação de tipo. |
| **ASGI** | O padrão de servidor assíncrono em Python. |
| **async / await** | Como Python espera por I/O sem travar o resto. |
| **Closure** | Função que lembra variáveis do escopo onde foi criada. Aqui: os nós lembram a `session`. |
| **Gravação** | Os passos que deram certo nesta sessão, ainda não salvos em arquivo. |
| **Teste salvo** | Um `testes/*.json`: a gravação congelada, com o seletor de cada passo. |
| **Replay** | Reexecutar um teste salvo. Repete as ações gravadas, sem chamar a LLM. |
| **Slug** | A versão higienizada do nome (`Login inválido` → `login-invalido`), usada como nome de arquivo. |
| **Lookahead / lookbehind** | Regex que confere o que vem antes/depois **sem consumir**. |
| **Regex crua (`r"..."`)** | String em que a barra invertida é literal. Obrigatório em regex. |

---

# Resumo em uma página

**O que tem de IA aqui:** duas chamadas de LLM por comando, cada uma respondendo a uma
pergunta fechada.

1. *Que ação é esta?* → uma de seis
2. *Qual elemento da página?* → um id de uma lista lida do DOM vivo

**O que NÃO é IA:** dividir a mensagem em comandos, extrair valores, gerar seletores,
verificar seletores, decidir a rota do grafo, desempatar formulários, esperar a página,
validar texto. Tudo isso é código determinístico.

**E quando o teste é salvo, nada é IA.** A LLM decidiu uma vez, na conversa; a decisão
ficou gravada com o seletor já provado contra a página. Reexecutar é percorrer essa lista
— zero chamadas ao Ollama. O que se ganha é um teste rápido e repetível; o que se perde é
a capacidade de se adaptar, que num teste é justamente o que não se quer.

**Por que assim:** porque eu medi o `qwen3:1.7b` antes de projetar. Ele degenera com
tarefa grande e corrompe dado literal, mas é confiável escolhendo item de lista curta. A
arquitetura é o formato dessa medição.

**A frase que resume:** *a LLM decide, o código determinístico executa.*

**O que isso compra:** um agente que roda de graça na sua máquina, que erra de forma
visível em vez de silenciosa, cujo seletor você pode copiar direto para um teste
Playwright de verdade — e que, quando o cenário funciona, guarda o caminho inteiro num
arquivo para rodar de novo quando você quiser.
