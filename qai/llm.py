"""Wrapper do ChatOllama.

As chamadas sao pequenas e com saida restrita por JSON Schema. Isso nao e estilo, e
uma limitacao medida do modelo local: com pergunta grande e resposta livre o
qwen3:1.7b degenera; com uma decisao por vez e lista fechada de respostas, acerta.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from .config import settings

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def enum_schema(**props: Iterable[str]) -> dict[str, Any]:
    """JSON Schema de objeto cujos campos so aceitam valores de listas fechadas."""
    return {
        "type": "object",
        "properties": {k: {"type": "string", "enum": list(v)} for k, v in props.items()},
        "required": list(props),
    }


async def classify(
    *,
    system: str,
    examples: list[tuple[str, str]],
    user: str,
    schema: dict[str, Any],
    run_name: str,
) -> dict[str, Any]:
    """Uma decisao restrita. Retorna {} se o modelo nao devolver JSON valido."""
    llm = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
        num_ctx=settings.ollama_num_ctx,
        reasoning=False,  # desliga o <think> do qwen3
        format=schema,
        num_predict=128,
    )

    messages: list[BaseMessage] = [SystemMessage(content=system)]
    for example_in, example_out in examples:
        messages.append(HumanMessage(content=example_in))
        messages.append(AIMessage(content=example_out))
    messages.append(HumanMessage(content=user))

    response = await llm.ainvoke(messages, config={"run_name": run_name})
    raw = _THINK_RE.sub("", str(response.content)).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def health_check() -> tuple[bool, str]:
    """Confere que o Ollama responde e que o modelo configurado existe."""
    try:
        import ollama

        client = ollama.Client(host=settings.ollama_base_url)
        available = {m.get("model") or m.get("name") for m in client.list().get("models", [])}
    except Exception as exc:  # noqa: BLE001 - a mensagem crua ajuda o usuario
        return False, f"Ollama nao respondeu em {settings.ollama_base_url}: {exc}"

    if settings.ollama_model not in available:
        return False, (
            f"Modelo '{settings.ollama_model}' nao encontrado. "
            f"Rode: ollama pull {settings.ollama_model}"
        )
    return True, f"Ollama OK, modelo {settings.ollama_model}"
