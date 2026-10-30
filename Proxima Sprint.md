# Estimativa — Serviço de Agente LLM + Playwright


## Descrição das Atividades

**1 -** **Setup do ambiente** Criar o projeto FastAPI do zero: estrutura de pastas, ambiente virtual, dependências (FastAPI, Uvicorn, Playwright, LangChain/LangGraph e os SDKs dos provedores), configuração por `.env` (chaves de API, conexão com o banco, endereço do browser remoto), conexão com o banco, servidor rodando localmente com uma rota de health e o README de como subir o projeto.


**2 -** **Camada de LLM com vários provedores** Fábrica que lê o provedor, o modelo e a chave no banco, para suportar diversos tipos de modelos sem mudar o código do agente: trocar de modelo ou de provedor é só mudar o registro no banco. Começa com Claude, OpenAI e Gemini (`langchain-anthropic`, `langchain-openai`, `langchain-google-genai`), e um provedor novo entra adicionando só a integração dele na fábrica. Saída estruturada com `with_structured_output`. Tratamento de timeout, retry e rate limit.


 **3 -** **Conexão com o browser remoto** Conectar via CDP (`connect_over_cdp`) no Playwright aberto no outro servidor, escolher a página certa, reconectar quando cair e isolar uma sessão por requisição.


**4** **Leitura da página** Montar a lista de elementos interativos a partir do DOM (papel, label, placeholder, formulário), gerar seletores candidatos e aceitar só os que apontam para um único elemento na página real. Esperar a página estabilizar depois de cada ação.


**5** **Interpretação do comando pela LLM** Classificar a ação (abrir, preencher, clicar, validar, limpar, localizar) e escolher o elemento a partir da lista lida da página. Checagens sem LLM: plausibilidade da escolha, desempate entre formulários e elemento não encontrado.


**6** **Extração de valores sem LLM**  Recortar URL, e-mail, senha e texto esperado do prompt com regex, para que dado de teste nunca passe pela LLM.

**7** **Execução das ações** Executar no Playwright (goto, fill, click, clear, expect_text) e gerar o código Playwright equivalente para o mapeamento, com mensagens de erro claras.
