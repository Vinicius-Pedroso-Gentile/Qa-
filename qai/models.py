"""Modelos de dados do agente interativo."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class Action(str, Enum):
    GOTO = "goto"
    FILL = "fill"
    CLICK = "click"
    EXPECT_TEXT = "expect_text"
    LOCATE = "locate"
    CLEAR = "clear"
    # Estas duas so nascem do record: escolher numa lista e apertar Enter num campo.
    SELECT = "select"
    PRESS = "press"

    @property
    def needs_element(self) -> bool:
        return self in (Action.FILL, Action.CLICK, Action.LOCATE, Action.CLEAR,
                        Action.SELECT, Action.PRESS)


# O que a LLM pode escolher no chat. Fica fixo de proposito: a lista fechada e os
# exemplos do prompt foram medidos com estas seis, e uma opcao nova no enum e uma
# resposta errada a mais que o modelo pequeno passa a poder dar.
CHAT_ACTIONS = (Action.GOTO, Action.FILL, Action.CLICK, Action.EXPECT_TEXT,
                Action.LOCATE, Action.CLEAR)

# Passos cujo valor pode ser corrigido depois de gravado, sem regravar.
EDITABLE_ACTIONS = (Action.GOTO, Action.FILL, Action.EXPECT_TEXT, Action.SELECT)

ACTION_LABEL = {
    Action.GOTO: "abrir URL",
    Action.FILL: "preencher",
    Action.CLICK: "clicar",
    Action.EXPECT_TEXT: "validar texto",
    Action.LOCATE: "localizar",
    Action.CLEAR: "limpar",
    Action.SELECT: "selecionar",
    Action.PRESS: "pressionar",
}


class Selector(BaseModel):
    """Como chegar a um elemento. Guardado estruturado para poder virar tanto um
    locator de verdade quanto o trecho de codigo que mostramos ao usuario."""

    kind: Literal["placeholder", "label", "role", "css", "text"]
    value: str
    name: str = ""  # so para kind="role": o nome acessivel
    form: str = ""  # escopo opcional no formulario, pelo texto do botao de submit
    nth: int | None = None  # ultimo recurso: fixa a posicao quando nada mais desempata
    # So para kind="role". Botao com icone de fonte (Font Awesome) tem o glifo do icone
    # no nome acessivel -- " Login" --, e o nome exato nunca casa com "Login".
    exact: bool = True

    def to_code(self) -> str:
        return self._expr() if self.nth is None else f"{self._expr()}.nth({self.nth})"

    def _expr(self) -> str:
        base = f'page.locator(\'form:has(button:text-is("{self.form}"))\')' if self.form else "page"
        if self.kind == "placeholder":
            return f"{base}.get_by_placeholder({self.value!r}, exact=True)"
        if self.kind == "label":
            return f"{base}.get_by_label({self.value!r}, exact=True)"
        if self.kind == "role":
            if not self.exact:
                return f"{base}.get_by_role({self.value!r}, name={self.name!r})"
            return f"{base}.get_by_role({self.value!r}, name={self.name!r}, exact=True)"
        if self.kind == "text":
            return f"{base}.get_by_text({self.value!r}, exact=True)"
        return f"{base}.locator({self.value!r})"


class PageElement(BaseModel):
    """Um elemento interativo real, lido da pagina em execucao."""

    element_id: str
    role: str = ""
    name: str = ""
    input_type: str = ""
    form: str = ""
    editable: bool = False
    selector: Selector

    def describe(self) -> str:
        bits = [self.role or "elemento"]
        if self.name:
            bits.append(f'"{self.name}"')
        if self.form:
            bits.append(f"[{self.form}]")
        return " ".join(bits)


class CommandResult(BaseModel):
    """O que responder ao usuario depois de um comando."""

    ok: bool
    message: str
    action: Optional[Action] = None
    selector_code: str = ""
    value: str = ""


class Step(BaseModel):
    """Um passo ja resolvido: a acao e o seletor que o Playwright provou resolver.

    E o que sobra de um comando depois que a LLM fez o trabalho dela. Guardado assim,
    o passo nao precisa ser interpretado de novo -- roda direto.
    """

    action: Action
    text: str = ""          # o comando original, so para leitura humana
    value: str = ""
    selector: Optional[Selector] = None
    element_name: str = ""
    element_form: str = ""
    # O trecho de Playwright que de fato rodou. Uma validacao de texto nao tem
    # elemento, so um matcher -- sem isto ela ficaria sem codigo nenhum no arquivo.
    code: str = ""
    # A pagina em que o passo comecou. E o que diz onde um bloco precisa estar para rodar.
    url: str = ""

    @property
    def selector_code(self) -> str:
        if self.code:
            return self.code
        return self.selector.to_code() if self.selector else ""

    @property
    def label(self) -> str:
        alvo = self.element_name or self.value
        rotulo = ACTION_LABEL.get(self.action, self.action.value)
        return f"{rotulo}: {alvo}" if alvo else rotulo

    def to_element(self) -> Optional[PageElement]:
        """O elemento sintetico que a sessao precisa para montar o locator."""
        if self.selector is None:
            return None
        return PageElement(
            element_id="gravado",
            name=self.element_name,
            form=self.element_form,
            selector=self.selector,
        )


class Block(BaseModel):
    """Um trecho reutilizavel de teste -- "Login", "Cadastrar usuario".

    Os testes guardam so a referencia (o slug). Corrigir o bloco corrige, de uma vez,
    todo teste que o usa; copiar os passos para dentro de cada teste obrigaria a
    procurar e consertar cada copia quando a tela mudasse.
    """

    name: str
    slug: str
    created_at: str
    url_inicial: str = ""
    steps: list[Step] = []


class Item(BaseModel):
    """Um item do teste: um passo solto ou um bloco (pelo slug)."""

    kind: Literal["step", "block"]
    step: Optional[Step] = None
    block: str = ""


class TestCase(BaseModel):
    """Um teste salvo: passos soltos e blocos, na ordem em que rodam."""

    name: str
    slug: str
    created_at: str
    # Onde o fluxo comecava. Um teste pode nao abrir a pagina no primeiro passo
    # ("preencher o e-mail") -- sem isto o primeiro seletor nao teria onde procurar.
    url_inicial: str = ""
    items: list[Item] = []
    # Formato antigo, anterior aos blocos: so passos. Continua sendo lido para os testes
    # ja salvos nao quebrarem; ao carregar, vira `items`.
    steps: list[Step] = []

    @model_validator(mode="after")
    def _migrar_passos(self) -> "TestCase":
        if not self.items and self.steps:
            self.items = [Item(kind="step", step=s) for s in self.steps]
            self.steps = []
        return self
