"""Configuracao lida do .env."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM local
    ollama_model: str = "qwen3:1.7b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_temperature: float = 0.0
    ollama_num_ctx: int = 8192

    # Observabilidade
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "qai-poc"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # Servidor
    host: str = "127.0.0.1"
    port: int = 8000
    # A tela do browser aparece dentro do proprio chat, entao por padrao nao abrimos
    # uma janela separada. HEADLESS=false volta a mostrar o Chromium de verdade.
    headless: bool = True


settings = Settings()


def configure_langsmith() -> bool:
    """Liga o tracing do LangSmith. Retorna se ficou ativo."""
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        os.environ["LANGSMITH_TRACING"] = "false"
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    return True
