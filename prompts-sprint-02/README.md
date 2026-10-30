# Prompts da Sprint 02 — Orquestrador

Prompts para uma IA implementar, do zero, o **Serviço de Agente LLM + Playwright**, seguindo
as decisões e as lições da POC Qaí.

## Arquivos

| Arquivo | Tarefa | Depende de |
|---|---|---|
| `00-contexto.md` | Contexto geral: objetivo, arquitetura, regras, stack, modelos de dados | — |
| `01-setup-ambiente.md` | Setup do ambiente FastAPI | — |
| `02-camada-llm.md` | Camada de LLM com vários provedores | 1 |
| `03-browser-remoto.md` | Conexão com o browser remoto via CDP | 1 |
| `04-leitura-pagina.md` | Leitura da página e seletores validados | 3 |
| `05-interpretacao-comando.md` | Interpretação do comando pela LLM | 2, 4 |
| `06-extracao-valores.md` | Extração de valores sem LLM | 1 (pode correr em paralelo) |
| `07-execucao-acoes.md` | Execução das ações + teste de ponta a ponta | 3, 4, 5, 6 |

## Antes de começar

Preencha a seção **"10. Decisões em aberto"** do `00-contexto.md` (banco, tabela de
configuração de LLM, formato da sessão do Playwright e criptografia da chave). Os
prompts mandam a IA **perguntar** quando encontrar um `[PREENCHER]`, mas preencher antes
evita idas e voltas.

## Como usar

1. Em cada conversa nova com a IA, envie **o `00-contexto.md` + o prompt da tarefa**.
   Exemplo de mensagem:
   > Leia o contexto e execute a tarefa abaixo. Ao terminar, confira os critérios de aceite um por um.
   >
   > [conteúdo do 00-contexto.md]
   >
   > [conteúdo do 0X-....md]
2. **Uma tarefa por conversa** (ou por PR). Misturar tarefas dilui o contexto e a IA
   começa a pular regras.
3. A IA mantém o `PROGRESSO.md` no repositório novo. É ele que passa o que já foi feito de
   uma tarefa para a outra. Se a próxima conversa não tiver acesso ao repositório, cole
   o `PROGRESSO.md` junto.
4. Só avance quando os **critérios de aceite** da tarefa estiverem passando.

## Ordem sugerida

```
1 ──► 2 ──────────────┐
  │                   ▼
  ├─► 3 ──► 4 ──────► 5 ──► 7
  │                         ▲
  └─► 6 ────────────────────┘
```

A tarefa 6 não depende de LLM nem de browser, então dá para fazer em paralelo com qualquer
outra.
