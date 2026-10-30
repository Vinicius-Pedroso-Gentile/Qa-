# Tarefa 1 — Setup do ambiente

> Pré-requisito: leia `00-contexto.md` inteiro antes de começar.

## Objetivo

Criar o projeto FastAPI **do zero**, pronto para as próximas tarefas: estrutura de pastas,
ambiente virtual, dependências, configuração por `.env`, conexão com o banco, servidor
rodando localmente com uma rota de health e o README de como subir o projeto.

**Nenhuma lógica de agente nesta tarefa.** Só o esqueleto que as tarefas 2 a 7 vão preencher.

---

## O que fazer

### 1. Estrutura

Crie a estrutura da seção 5 do contexto, com `__init__.py` nos pacotes e módulos vazios
(só docstring dizendo para que servem) onde as próximas tarefas vão escrever:

```
app/main.py
app/config.py
app/db.py
app/llm/__init__.py
app/browser/__init__.py
app/agent/__init__.py
tests/
scripts/
```

### 2. Dependências

Use `pyproject.toml` (preferido) ou `requirements.txt`, com versões mínimas:

```
fastapi
uvicorn[standard]
pydantic>=2
pydantic-settings
playwright
langchain-core
langchain              # para init_chat_model
langchain-anthropic
langchain-openai
langchain-google-genai
langgraph              # usado na próxima sprint, mas já entra no ambiente
langsmith
[driver do banco — ver D1 no contexto]

# dev
pytest
pytest-asyncio
httpx                  # TestClient async
ruff
```

O README deve dizer para rodar `playwright install chromium`. Mesmo usando browser
remoto, o pacote precisa estar instalado, e os testes de integração locais usam um
Chromium próprio.

### 3. Configuração (`app/config.py`)

Uma classe `Settings(BaseSettings)` com instância única `settings`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",       # ROOT ancorado em __file__, não no diretório atual
        env_file_encoding="utf-8",    # Windows: sem isso um acento no .env quebra a leitura
        extra="ignore",
        case_sensitive=False,
    )

    # Servidor
    host: str = "127.0.0.1"           # não 0.0.0.0 por padrão: o serviço controla browsers
    port: int = 8000
    log_level: str = "info"

    # Banco
    database_url: str                 # obrigatório: falha ao subir se não existir

    # Browser remoto (padrão; a requisição pode trazer o seu)
    browser_cdp_url: str = ""

    # LLM: valores padrão quando a configuração do banco não disser
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 3

    # Observabilidade
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "orquestrador"
```

Uma função `configure_langsmith()` que só liga o tracing se **a flag e a chave** estiverem
preenchidas. Ela deve escrever `LANGSMITH_TRACING="false"` explicitamente quando estiver
desligado, para uma variável esquecida no terminal não ligar o tracing sem querer.

Crie o `.env.example` com todas as variáveis, comentadas, e sem valores secretos.
Coloque o `.env` no `.gitignore`.

### 4. Banco (`app/db.py`)

- Crie o engine/pool a partir de `settings.database_url` (ver **D1**).
- Exponha uma função de "ping" (`SELECT 1`) para o health.
- Abra no `lifespan` do FastAPI e feche no desligamento.
- **Não** crie tabelas nem migrations nesta tarefa. Isso está fora da estimativa.

### 5. App (`app/main.py`)

- Use `lifespan`, **não** `@app.on_event` (deprecado).
- Rota `GET /health` retornando:
  ```json
  { "status": "ok", "db": "ok", "version": "0.1.0" }
  ```
  Se o banco não responder, retorne `503` com `"db": "erro: <mensagem curta>"`. Nunca
  exponha a connection string.
- Logging configurado uma vez, no formato `nível | módulo | mensagem`.
- Ponto de entrada: `python -m app` (crie `app/__main__.py` chamando `uvicorn.run`).

### 6. README

Instruções do zero até o `/health` respondendo:
1. criar e ativar o venv (Windows e Linux);
2. instalar as dependências;
3. `playwright install chromium`;
4. copiar o `.env.example` para `.env` e preencher;
5. subir com `python -m app`;
6. testar com `curl http://127.0.0.1:8000/health`;
7. rodar os testes com `pytest` (e como pular os de integração).

### 7. PROGRESSO.md

Crie o arquivo com as seções: **Feito**, **Decisões**, **Pendências**, **Como testar**.

---

## Fora do escopo

- Tabelas, modelos ORM e migrations.
- Qualquer chamada de LLM ou de browser.
- Outras rotas além de `/health`.
- Docker (fica para depois).

---

## Critérios de aceite

- [ ] Um clone limpo + os passos do README sobem o servidor sem erro.
- [ ] `GET /health` responde `200` com o banco no ar e `503` com o banco fora, sem vazar a connection string.
- [ ] Subir sem `DATABASE_URL` falha **na hora**, com mensagem clara dizendo qual variável falta.
- [ ] `.env` está no `.gitignore` e o `.env.example` lista todas as variáveis.
- [ ] `pytest` roda e passa, com pelo menos um teste do `/health` (banco mockado).
- [ ] `ruff check` passa.
- [ ] `PROGRESSO.md` criado e preenchido.
