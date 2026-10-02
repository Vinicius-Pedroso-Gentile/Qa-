"""O ciclo de um comando, como um grafo LangGraph.

    interpretar --> preparar --> executar --> fim
         |
         +-- (pediu um elemento que nao existe na pagina) --> faltou_elemento --> fim

O grafo e construido ja amarrado a uma sessao de browser, entao os nos sao fechamentos
sobre ela -- nao precisa carregar objeto de browser dentro do estado.

Quem de fato mexe na pagina e o `actions.py`: os nos daqui so decidem *o que* fazer.
Assim o teste salvo, que pula a interpretacao inteira, repete a acao pelo mesmo
caminho que a gravou.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from .actions import run_action, run_expect_text
from .browser import BrowserSession
from .interpreter import (
    choose_action,
    choose_element,
    disambiguate,
    only_text_field,
    parece_validacao,
)
from .literals import extract_value
from .models import Action, CommandResult, PageElement


class CommandState(TypedDict, total=False):
    text: str
    action: Action
    element: Optional[PageElement]
    value: Optional[str]
    result: CommandResult


def build_graph(session: BrowserSession):
    async def interpretar(state: CommandState) -> dict:
        action = await choose_action(state["text"])
        if action == Action.EXPECT_TEXT and not parece_validacao(state["text"]):
            action = Action.FILL
        element = None
        if action.needs_element and session.elements:
            element = await choose_element(state["text"], session.elements)
            element = disambiguate(element, session.elements, session.active_form)
            if element is None and action == Action.FILL:
                element = only_text_field(session.elements)
            if element is None and action == Action.CLEAR:
                # "apague isso" nao nomeia campo nenhum: vale o ultimo em que mexemos.
                element = session.last_element or only_text_field(session.elements)
        return {"action": action, "element": element}

    async def preparar(state: CommandState) -> dict:
        element = state.get("element")
        value = extract_value(
            state["text"],
            state["action"].value,
            element_label=element.name if element else "",
        )
        return {"value": value}

    async def executar(state: CommandState) -> dict:
        return {"result": await run_action(
            session, state["action"], state.get("element"), state.get("value"),
        )}

    async def validar_texto(state: CommandState) -> dict:
        return {"result": await run_expect_text(session, state.get("value"))}

    async def faltou_elemento(state: CommandState) -> dict:
        disponiveis = ", ".join(f'"{e.name}"' for e in session.elements[:6]) or "nenhum"
        return {"result": CommandResult(
            ok=False,
            message=f"Nao achei esse elemento na pagina. Disponiveis: {disponiveis}.",
        )}

    def rota(state: CommandState) -> str:
        action = state["action"]
        if action == Action.EXPECT_TEXT:
            return "validar"
        if action.needs_element and state.get("element") is None:
            return "faltou"
        return "seguir"

    builder = StateGraph(CommandState)
    builder.add_node("interpretar", interpretar)
    builder.add_node("preparar", preparar)
    builder.add_node("executar", executar)
    builder.add_node("validar_texto", validar_texto)
    builder.add_node("faltou_elemento", faltou_elemento)

    builder.set_entry_point("interpretar")
    builder.add_conditional_edges(
        "interpretar",
        rota,
        {"seguir": "preparar", "validar": "preparar", "faltou": "faltou_elemento"},
    )
    builder.add_conditional_edges(
        "preparar",
        lambda s: "validar" if s["action"] == Action.EXPECT_TEXT else "executar",
        {"validar": "validar_texto", "executar": "executar"},
    )
    builder.add_edge("executar", END)
    builder.add_edge("validar_texto", END)
    builder.add_edge("faltou_elemento", END)

    return builder.compile()
