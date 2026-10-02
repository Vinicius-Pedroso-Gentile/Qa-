# Qaí — agente de teste conversacional

Um chat no navegador onde você dá comandos em português e o **Playwright executa na sua
frente**, passo a passo, numa janela de browser real.

```
você: https://bugbank.netlify.app/
  →   Abri https://bugbank.netlify.app/ — mapeei 11 elementos na página.

você: Informar o e-mail qualquerCoisa0001@gmail.com
  →   Preenchi "Informe seu e-mail" com qualquerCoisa0001@gmail.com
      page.locator('form:has(button:text-is("Acessar"))').get_by_placeholder('Informe seu e-mail', exact=True)

você: Clicar no botão "Acessar"
  →   Cliquei em "Acessar"

você: Validar que aparece a mensagem: "Usuário ou senha inválido..."
  →   ✓ A mensagem está na tela
```

LLM **100% local** via Ollama (`qwen3:1.7b`), orquestração em **LangGraph**, tracing em
**LangSmith**. Nada sai da máquina.

## Rodar

```powershell
.venv\Scripts\python.exe -m qai
```

Abra **http://127.0.0.1:8000** no Chrome. **A tela do browser aparece dentro da própria
página do chat**, ao vivo — não abre janela separada.

Se preferir mostrar o Chromium de verdade na apresentação, ponha `HEADLESS=false` no `.env`:
aí a janela abre também, e a tela embutida continua funcionando.

Primeira instalação:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

O `.env` é opcional — só precisa dele para ligar o LangSmith ou trocar o modelo.

## Frontend (React + TypeScript)

A interface fica em `frontend/` (Vite + React + TypeScript). O `npm run build` gera os
arquivos em `qai/web/dist/`, e o próprio FastAPI serve essa pasta — ou seja, **depois do
build, `python -m qai` basta**, sem Node rodando.

Primeira vez (precisa do [Node.js](https://nodejs.org/) LTS):

```powershell
cd frontend
npm install
npm run build
```

Para mexer no frontend com recarga automática, rode o servidor Python normalmente e, em
outro terminal:

```powershell
cd frontend
npm run dev
```

e abra **http://localhost:5173** — o Vite repassa as chamadas `/api` para o FastAPI na 8000.

O chat fica escondido até você clicar em **Usar o chat** (no topo ou na tela de início).

## Record

Clique em **Record** e use a tela do browser como se fosse o site: clique nos campos, digite,
clique nos botões. Cada ação vira um passo no **Teste em construção**.

- **Interagir**: cliques e digitação. Várias teclas no mesmo campo viram um único
  "preencher" com o valor final (Backspace incluído).
- **Validar texto**: clique num texto da tela e ele vira um "esse texto tem que aparecer".
- Clique num `<select>` abre a lista de opções na própria tela.

Antes de cada clique, o elemento é identificado e o seletor é testado contra a página
viva; o clique então é feito **pelo seletor**. Um passo gravado já funcionou uma vez.
Nenhuma LLM participa do record.

## Blocos

No **Teste em construção**, marque passos e clique em **Criar bloco** (ex.: "Login"). Os
passos viram um bloco em `blocos/<nome>.json` e, no teste, uma referência a ele. No painel
**Blocos**, **Usar** põe o bloco no teste que está sendo montado.

O teste guarda a referência, não uma cópia: se a tela de login mudar, regrave os passos,
crie o bloco com o mesmo nome e confirme a substituição — todo teste que usa "Login" passa
a rodar a versão nova. Cada passo também pode ser editado (✎), movido ou removido antes de
salvar; numa validação com dado variável, troque o trecho por máscara (`XXXX-X`).

## Comandos que ele entende

| Você escreve | O que acontece |
|---|---|
| `https://algum-site.com` ou `Acessar a aplicação: ...` | abre a página e mapeia os elementos |
| `Localizar o campo "E-mail"` | confirma que o campo está na tela |
| `Informar o e-mail fulano@x.com` | preenche o campo |
| `Clicar no botão "Acessar"` | clica |
| `Validar que aparece a mensagem: "..."` | valida — e **reprova** se o texto não estiver lá |
| `Apague a uva` / `limpe o campo senha` | esvazia o campo |

### Validar mensagem com dado que muda

Mensagem de sistema costuma carregar um dado diferente a cada execução. Escreva a parte
variável como máscara — `XXXX-X`, `###`, `*`:

```
valide que aparece a mensagem: "A conta XXXX-X foi criada com sucesso"
  →  A mensagem está na tela (comparado com máscara)
     expect(page.get_by_text(re.compile('A\s+conta\s+\S+\s+foi\s+criada\s+com\s+sucesso')))
```

A máscara **não afrouxa a validação**: só o trecho mascarado vira curinga, todo o resto
continua comparado palavra por palavra. Trocar `criada` por `encerrada` reprova. O regex
gerado aparece no chat, para dar para conferir o que foi comparado de fato.

A máscara precisa ser uma palavra inteira (`XXXX-X`, e não `contaXXXX`) e ter ao menos dois
caracteres curinga — senão um hífen solto no meio de uma frase viraria máscara.

Várias ordens cabem em uma mensagem só, ligadas por `e`, `depois`, `então` ou vírgula:

```
informe o e-mail x@y.com, informe a senha Teste@123 e clique em Acessar
```

Cada ordem vira um passo numerado no chat. A cadeia **para no primeiro passo que falhar** —
continuar clicando depois de um preenchimento que não deu certo só produziria um segundo erro
sem sentido. A quebra é feita antes de qualquer LLM, em [commands.py](qai/commands.py): texto
entre aspas é protegido, e só há corte quando o trecho seguinte começa com um verbo de ação
(por isso `Nome com João e Maria` continua sendo um valor só).

O arquivo [scenarios/01-login-invalido.md](scenarios/01-login-invalido.md) é o roteiro de
demonstração: dá para digitar os passos dele, um por um, na ordem. Os mesmos comandos estão
como atalhos clicáveis abaixo do chat.

## Salvar o teste e rodar de novo

Enquanto você conversa, **todo comando que dá certo vira um passo gravado** — com o seletor
que o Playwright já provou resolver naquele elemento. O painel *Gravação do teste* mostra a
lista; o código que rodou fica no `title` de cada passo.

Terminado o fluxo, dê um nome e clique em **Salvar**. O teste vai para `testes/<nome>.json`,
um passo por ação:

```json
{
  "action": "fill",
  "text": "informe o e-mail qualquerCoisa0001@gmail.com",
  "value": "qualquerCoisa0001@gmail.com",
  "selector": { "kind": "placeholder", "value": "Informe seu e-mail", "form": "Acessar" },
  "element_name": "Informe seu e-mail",
  "code": "page.locator('form:has(button:text-is(\"Acessar\"))').get_by_placeholder('Informe seu e-mail', exact=True)"
}
```

Depois é só **▶ Rodar** na lista de testes salvos. A reexecução **não chama a LLM**: a
decisão já foi tomada e gravada, então o que sobra é o Playwright repetindo a sequência.

| | Conversando | Rodando um teste salvo |
|---|---|---|
| Quem escolhe o elemento | a LLM, conferida contra a página | ninguém — já está no arquivo |
| Chamadas ao Ollama | 2 por comando | zero |
| Se a página mudar | o agente se vira | o passo falha |

O que faz a reexecução dar certo:

- **O seletor gravado é o que foi verificado**, não o palpite do modelo — ele só entrou no
  inventário depois de resolver, sozinho, exatamente aquele elemento no DOM vivo. É a regra
  3 do projeto pagando o aluguel: o teste salvo vale porque o seletor nunca foi inventado.
- **A ação é executada pelo mesmo código** que a executou durante a conversa
  ([actions.py](qai/actions.py)). O chat decide *o que* fazer; quem faz é sempre o mesmo.
- **A URL de partida é anotada antes de o passo rodar.** Se o teste não começa abrindo a
  página, ele abre por conta própria — senão o primeiro seletor não teria onde procurar. E é
  gravada *antes* porque um clique que navega já teria trocado a URL.
- **Para no primeiro passo que falha**, pela mesma razão do chat, e diz quantos ficaram
  para trás.
- Só passo que **deu certo** é gravado: um comando que a LLM não entendeu não suja o teste.
- Salvar com um nome que já existe **sobrescreve** — é assim que se regrava um teste.

## Como funciona

```
comando em português
   → interpretar   (LLM: que ação é? qual elemento?)
      → preparar   (recorta o valor literal do comando)
         → executar / validar   (Playwright age na página)
            → remapeia a página para o próximo comando
               → deu certo? o passo entra na gravação, com o seletor usado
```

A gravação é o mesmo caminho lido de trás para frente: rodar um teste salvo entra direto
no `executar`, porque `interpretar` e `preparar` já rodaram uma vez — e o resultado deles
está no arquivo.

| Arquivo | Responsabilidade |
|---|---|
| [browser.py](qai/browser.py) | sessão do Playwright: abre, lê a página, age |
| [interpreter.py](qai/interpreter.py) | as duas perguntas que a LLM responde |
| [literals.py](qai/literals.py) | recorta e-mail, senha, URL e mensagem do comando |
| [graph.py](qai/graph.py) | o LangGraph que amarra o ciclo de um comando |
| [actions.py](qai/actions.py) | o que fazer na página, uma implementação só |
| [suite.py](qai/suite.py) | grava, salva e reexecuta um teste |
| [server.py](qai/server.py) | FastAPI + a página do chat |

### As três regras do projeto

Não são preferências de estilo — vêm de medições feitas com o `qwen3:1.7b` antes de escrever
o código:

| O que testei | Resultado |
|---|---|
| Saída restrita por JSON Schema | funciona — JSON sempre válido |
| Pedir à LLM que copie o dado de teste | **corrompeu**: `qualquerCoisa0001@gmail.com` → `anything0001@gmail.com` (traduziu) |
| Interpretação inteira em uma chamada | **degenerou**: repetiu a mesma ação em loop |
| Uma decisão por vez, enum + few-shot | **acerta** de forma consistente |

Daí:

1. **Perguntas pequenas.** Uma decisão por chamada, resposta restrita a uma lista fechada.
2. **Dado de teste nunca passa pela LLM.** Valores são recortados do comando por regra.
3. **Seletor nunca é inventado.** Cada elemento é carimbado na página e o seletor candidato
   só é aceito se, testado contra o DOM vivo, resolver para exatamente aquele elemento.

Trocar para um modelo maior é uma variável de ambiente (`OLLAMA_MODEL`); o código não muda.

### Armadilhas do BugBank que o código trata

- **Não existe `<label>` associado** — só `placeholder`. Por isso `get_by_placeholder` pesa
  na escolha do seletor.
- **O "Fechar" do modal não é um `<button>`** — é `<a id="btnCloseModal">`, âncora sem `href`.
  Por isso o inventário também recolhe `div/span/a` com `cursor: pointer`, e existe um seletor
  por texto visível, o único que funciona em elemento sem semântica.
- **Login e cadastro trocam virando um cartão 3D**, e os dois ficam no DOM o tempo todo. Os
  campos da face escondida continuam com tamanho e `visibility: visible` — checagem de CSS
  não os separa. O que separa é `document.elementFromPoint` no centro do elemento: só entra
  no inventário quem está de fato por cima. Foi o que fez o agente parar de preencher o
  formulário errado depois de clicar em "Registrar".

  O mesmo teste resolve o modal de graça: com ele aberto, o que está atrás some do inventário
  — que é exatamente o que não dá para clicar.

### Esperar a página terminar de mudar

Depois de cada ação o inventário é refeito — mas *quando* refazer é o problema difícil num
SPA. Medindo o BugBank, o mesmo clique de login levou **101ms numa execução e 376ms em
outra** para trocar de tela. Qualquer espera fixa erra em metade dos casos, e o sintoma é
cruel: o agente responde com confiança usando os elementos da tela anterior.

Amostrar a página de tempos em tempos também não resolve — uma pausa entre dois renders
parece "estável".

O sinal confiável é o próprio navegador avisar. Um `MutationObserver` marca a hora da última
alteração no DOM, e a página só é considerada pronta quando faz meio segundo que nada muda.
Depois de uma navegação o `window` é novo, o observador se reinstala e o contador zera — que
é exatamente o certo, porque acabou de mudar tudo.

Testado em três execuções seguidas do fluxo completo (login → home → transferência → voltar):
3/3 com o inventário certo em cada tela.

### Quando ele não entende

O enum obriga o modelo a escolher um id válido, então ele sempre escolhe algo — pedir
"clicar no botão Transferência" numa página sem esse botão fazia ele responder "Cadastrar".
Por isso a escolha da LLM é conferida contra o texto do comando: sem nenhuma palavra em
comum, a resposta vira "não achei esse elemento", com a lista do que existe na página.

## LangSmith

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=qai-poc
```

Cada comando vira um trace `comando_qai`, com um span por nó do grafo e um span por
chamada de LLM (`escolher_acao`, `escolher_elemento`) — prompt, resposta e latência.

### Não existe histórico de conversa

Cada comando é interpretado **isolado**. A LLM não recebe as mensagens anteriores — ela vê
só o comando atual e o inventário da página. Então "faça de novo", "desfaça o que eu pedi"
ou "use o mesmo valor de antes" não funcionam.

É uma decisão, não um esquecimento: mandar histórico para um modelo de 1.7B é exatamente o
tipo de entrada grande que o faz degenerar. O que carrega o contexto é **a própria página**,
que é relida a cada comando, mais dois ponteiros na sessão:

| O que a sessão lembra | Para quê |
|---|---|
| `active_form` | o formulário em que você está trabalhando, para desempatar campos repetidos |
| `last_element` | o último campo tocado, para `apague isso` saber do que se trata |

## Limites

- Uma sessão de browser por vez (é um agente local, de um usuário só).
- O teste salvo repete exatamente o que foi gravado — ele **não se adapta**. Se a página
  mudar de verdade, o passo falha em vez de procurar outro caminho. Para regravá-lo, faça
  o fluxo de novo no chat e salve com o mesmo nome.
- Alvo externo: se o site sair do ar, não tem o que fazer.
