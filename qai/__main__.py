"""Sobe o servidor do chat."""

from __future__ import annotations

import sys

from .config import configure_langsmith, settings
from .llm import health_check


def main() -> int:


    # Aqui é só pra eu fazer prints bonitinhos
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - terminal antigo
        pass

    healthy, message = health_check()
    if not healthy:
        print(f"Ollama indisponivel: {message}")
        return 2

    tracing = configure_langsmith()
    url = f"http://{settings.host}:{settings.port}"

    print("\n  Qaí — agente de teste")
    print(f"  LLM ......: {settings.ollama_model}")
    print(f"  LangSmith : {'ativo (' + settings.langsmith_project + ')' if tracing else 'desligado'}")
    print(f"  Abra no Chrome: {url}\n")

    from .server import serve

    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
