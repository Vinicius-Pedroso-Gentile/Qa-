# Estimativa — Serviço de Agente LLM + Playwright

Serviço em FastAPI que recebe os dados de uma sessão do Playwright (aberta em outro servidor) e o
prompt do usuário, **interpreta, valida e executa** a ação na página e salva no banco o mapeamento
gerado. O modelo de LLM é definido no banco e pode ser **Claude, OpenAI ou Gemini**.

| # | Atividade | Descrição | Horas |
|:-:|---|---|:-:|
| **1** | **Camada de LLM com vários provedores** | Fábrica que lê o provedor, o modelo e a chave no banco e suporta Claude, OpenAI e Gemini (`langchain-anthropic`, `langchain-openai`, `langchain-google-genai`). Saída estruturada com `with_structured_output`. Tratamento de timeout, retry e rate limit | **12 – 16** |
| **2** | **Conexão com o browser remoto** | Conectar via CDP (`connect_over_cdp`) no Playwright aberto no outro servidor, escolher a página certa, reconectar quando cair e isolar uma sessão por requisição | **8 – 16** |
| **3** | **Leitura da página** | Montar a lista de elementos interativos a partir do DOM (papel, label, placeholder, formulário), gerar seletores candidatos e aceitar só os que apontam para um único elemento na página real. Esperar a página estabilizar depois de cada ação | **24 – 32** |
| **4** | **Interpretação do comando pela LLM** | Classificar a ação (abrir, preencher, clicar, validar, limpar, localizar) e escolher o elemento a partir da lista lida da página. Checagens sem LLM: plausibilidade da escolha, desempate entre formulários e elemento não encontrado | **16 – 24** |
| **5** | **Extração de valores sem LLM** | Recortar URL, e-mail, senha e texto esperado do prompt com regex, para que dado de teste nunca passe pela LLM | **8 – 12** |
| **6** | **Execução das ações** | Executar no Playwright (`goto`, `fill`, `click`, `clear`, `expect_text`) e gerar o código Playwright equivalente para o mapeamento, com mensagens de erro claras | **12 – 16** |
| **7** | **Fluxo do agente (LangGraph)** | Interpretar → preparar → executar, com as rotas de falha. Quebrar um prompt em vários comandos e parar no primeiro erro | **8 – 12** |
| **8** | **Endpoints** | `POST /executar` (dados da sessão + prompt → valida → age → salva), consulta do mapeamento e health | **8** |
| **9** | **Persistência** | Salvar no banco as ações executadas e o mapeamento gerado | **6 – 8** |
| **10** | **Ajuste de prompts por provedor** | Rodar cenários reais em Claude, GPT e Gemini e ajustar prompts e exemplos, já que cada modelo erra de um jeito diferente | **16 – 24** |
| | | **Total** | **118 – 168 h** |

> **≈ 15 a 21 dias úteis · 3 a 4 semanas para 1 dev**

## Premissas

- O browser remoto expõe um endpoint **CDP/WebSocket**. Se ele só expuser ações por HTTP, somar **24 – 40 h**.
- A estrutura do banco (modelos e migrations) e a infraestrutura **não estão incluídas**.
- Testes automatizados, logs e tracing, Docker e documentação **não estão incluídos** (estimativa à parte: 16 – 24 h).
- A resposta é **síncrona**. Se precisar de fila (job assíncrono com polling ou webhook), somar **8 – 16 h**.
