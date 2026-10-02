"""As acoes que o agente sabe executar na pagina.

Ficam fora do grafo de proposito. O mesmo despacho atende dois caminhos: o comando
que acabou de ser interpretado pela LLM e o passo de um teste salvo, que ja chega
com o seletor resolvido. Uma implementacao so -- senao o teste gravado executaria um
clique um pouco diferente do clique que foi gravado, e a gravacao deixaria de valer
como prova de que aquilo funciona.
"""

from __future__ import annotations

from typing import Optional

from .browser import BrowserSession
from .literals import to_pattern
from .models import Action, CommandResult, PageElement
from .textutil import normalize


def erro_curto(exc: Exception) -> str:
    """Playwright despeja um call log enorme; no chat cabe a primeira linha."""
    texto = str(exc)
    primeira = texto.strip().splitlines()[0] if texto.strip() else "erro desconhecido"
    if "intercepts pointer events" in texto:
        return f"{primeira} Tem algo na frente do elemento (um modal aberto?)."
    if "Timeout" in primeira:
        return f"{primeira} O elemento nao ficou disponivel a tempo."
    return primeira


async def run_action(
    session: BrowserSession,
    action: Action,
    element: Optional[PageElement],
    value: Optional[str],
) -> CommandResult:
    try:
        return await _despachar(session, action, element, value)
    except Exception as exc:  # noqa: BLE001 - vira mensagem de chat, nao stacktrace
        return CommandResult(ok=False, message=erro_curto(exc))


async def _despachar(
    session: BrowserSession,
    action: Action,
    element: Optional[PageElement],
    value: Optional[str],
) -> CommandResult:
    if action == Action.GOTO:
        if not value:
            return CommandResult(ok=False, message="Nao reconheci uma URL nesse comando.")
        await session.goto(value)
        found = await session.snapshot()
        session.active_form = ""
        return CommandResult(
            ok=True,
            action=action,
            value=value,
            message=f"Abri {value} — mapeei {len(found)} elementos na pagina.",
        )

    if element is None:
        return CommandResult(ok=False, message="Preciso abrir uma pagina antes.")

    if action == Action.FILL:
        if not value:
            return CommandResult(
                ok=False,
                message=f'Entendi que e para preencher "{element.name}", mas nao achei o valor no comando.',
            )
        await session.fill(element, value)
        await session.snapshot()
        session.active_form = element.form
        session.last_element = element
        return CommandResult(
            ok=True, action=action, value=value,
            selector_code=element.selector.to_code(),
            message=f'Preenchi "{element.name}" com {value}',
        )

    if action == Action.CLEAR:
        await session.clear(element)
        await session.snapshot()
        session.last_element = element
        return CommandResult(
            ok=True, action=action,
            selector_code=element.selector.to_code(),
            message=f'Limpei o campo "{element.name}"',
        )

    if action == Action.CLICK:
        await session.click(element)
        await session.snapshot()
        # So um botao de submit confirma em que formulario estamos. "Registrar" mora
        # dentro do formulario de login, mas clicar nele leva para o de cadastro --
        # manter "Acessar" como ativo faria os campos seguintes irem para a tela errada.
        ehSubmit = normalize(element.name) == normalize(element.form)
        session.active_form = element.form if ehSubmit else ""
        session.last_element = element
        return CommandResult(
            ok=True, action=action,
            selector_code=element.selector.to_code(),
            message=f'Cliquei em "{element.name}"',
        )

    if action == Action.SELECT:
        if not value:
            return CommandResult(ok=False, message=f'Faltou a opcao a escolher em "{element.name}".')
        await session.select(element, value)
        await session.snapshot()
        session.last_element = element
        return CommandResult(
            ok=True, action=action, value=value,
            selector_code=element.selector.to_code(),
            message=f'Selecionei "{value}" em "{element.name}"',
        )

    if action == Action.PRESS:
        tecla = value or "Enter"
        await session.press(element, tecla)
        await session.snapshot()
        session.last_element = element
        return CommandResult(
            ok=True, action=action, value=tecla,
            selector_code=element.selector.to_code(),
            message=f'Apertei {tecla} em "{element.name}"',
        )

    if action == Action.LOCATE:
        visivel = await session.is_visible(element)
        session.active_form = element.form if visivel else session.active_form
        return CommandResult(
            ok=visivel, action=action,
            selector_code=element.selector.to_code(),
            message=(f'Encontrei "{element.name}" na tela.' if visivel
                     else f'Nao consegui ver "{element.name}" na tela.'),
        )

    return CommandResult(ok=False, message="Nao sei executar esse comando.")


def codigo_expect(value: str) -> str:
    """O expect que corresponde a esta validacao. Separado para ser refeito quando o
    usuario corrige o texto de um passo ja gravado."""
    padrao = to_pattern(value)
    if padrao is None:
        return f"expect(page.get_by_text({value!r})).to_be_visible()"
    return f"expect(page.get_by_text(re.compile({padrao.pattern!r}))).to_be_visible()"


async def run_expect_text(session: BrowserSession, value: Optional[str]) -> CommandResult:
    if not value:
        return CommandResult(
            ok=False,
            message="Entendi que e uma validacao, mas nao achei o texto esperado. "
                    "Coloque a mensagem entre aspas.",
        )
    encontrado = await session.has_text(value)
    await session.snapshot()

    nota = "" if to_pattern(value) is None else " (comparado com máscara)"
    return CommandResult(
        ok=encontrado,
        action=Action.EXPECT_TEXT,
        value=value,
        selector_code=codigo_expect(value),
        message=(f'A mensagem esta na tela{nota}: "{value}"' if encontrado
                 else f'A mensagem NAO apareceu{nota}: "{value}"'),
    )
