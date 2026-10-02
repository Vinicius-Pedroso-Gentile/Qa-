"""Record: montar o teste mexendo na pagina, em vez de descrever em portugues.

O usuario clica e digita na tela embutida; cada gesto chega aqui como coordenada ou
tecla e vira uma acao do Playwright. O que muda em relacao a um gravador comum:

* O elemento e identificado ANTES da acao. Depois de um clique o modal pode ter
  fechado ou a tela trocado -- ai nao ha mais o elemento para descrever.
* O seletor passa pela mesma verificacao do snapshot: tem que resolver, sozinho,
  exatamente o elemento clicado.
* Antes do clique, um clique de ensaio pelo seletor (trial) confirma que o replay vai
  conseguir repeti-lo. O clique de verdade e o do usuario, na coordenada dele.

E nada espera a pagina assentar: o usuario esta olhando a tela e reage ao que ve.
Medido: esperar o DOM parar e remapear a pagina custava de 0,5s a 4s por clique --
identificar o elemento e verificar o seletor, 6 a 12ms.

Nenhuma LLM participa: o usuario ja disse o que queria fazer, com o mouse.
"""

from __future__ import annotations

from pydantic import BaseModel

from .actions import codigo_expect
from .browser import BrowserSession
from .models import Action, PageElement, Step
from .suite import Gravacao

# Teclas que mudam o conteudo do campo sem digitar um caractere.
_APAGAM = {"Backspace", "Delete"}


class Evento(BaseModel):
    """A resposta de um gesto do record."""

    ok: bool
    message: str
    gravado: bool = False          # virou passo no teste em construcao?
    aviso: str = ""                # gravou, mas com ressalva que o usuario precisa ver
    selector_code: str = ""
    opcoes: list[dict] = []        # clique num <select>: a tela mostra as opcoes


def _mesmo_alvo(step: Step, element: PageElement) -> bool:
    return step.selector is not None and step.selector == element.selector


class Gravador:
    def __init__(self, session: BrowserSession, gravacao: Gravacao) -> None:
        self.session = session
        self.gravacao = gravacao
        # Clique num <select> nao abre lista nenhuma num browser headless: a tela
        # pergunta a opcao e ela chega depois, em selecionar().
        self._select_pendente: PageElement | None = None

    def _gravar(self, action: Action, element: PageElement | None, value: str,
                code: str, url: str, texto: str) -> None:
        self.gravacao.adicionar(Step(
            action=action,
            text=texto,
            value=value,
            selector=element.selector if element else None,
            element_name=element.name if element else "",
            element_form=element.form if element else "",
            code=code,
            url=url,
        ))

    async def clicar(self, x: float, y: float) -> Evento:
        url = self.session.current_url
        alvo = await self.session.elemento_em(x, y)

        if alvo is None or alvo.elemento is None:
            # Fundo da pagina, texto solto, ou algo sem seletor unico: o clique
            # acontece, mas nao vira passo -- um passo sem seletor nao se repete.
            await self.session.clicar_em(x, y)
            motivo = ("nao achei um seletor unico para ele" if alvo is not None and alvo.tag
                      else "nao ha elemento clicavel ali")
            return Evento(ok=True, message=f"Cliquei, mas nao gravei: {motivo}.")

        element = alvo.elemento
        if alvo.tag == "select":
            self._select_pendente = element
            return Evento(ok=True, message=f'Escolha uma opcao de "{element.name}".', opcoes=alvo.opcoes)

        if element.editable:
            # Clicar num campo so poe o foco nele. O passo nasce quando se digita.
            await self.session.clicar_em(x, y)
            return Evento(ok=True, message=f'Campo "{element.name}" em foco — pode digitar.')

        repetivel = await self.session.clicavel(element)
        await self.session.clicar_em(x, y)
        codigo = element.selector.to_code()
        self._gravar(Action.CLICK, element, "", codigo, url, f'clicar em "{element.name}"')
        aviso = "" if repetivel else (
            f'Gravei o clique em "{element.name}", mas o Playwright ve outro elemento por cima '
            "dele — no replay este passo pode falhar."
        )
        return Evento(ok=True, gravado=True, message=f'Cliquei em "{element.name}"',
                      aviso=aviso, selector_code=codigo)

    async def teclado(self, texto: str, tecla: str) -> Evento:
        url = self.session.current_url
        foco = await self.session.elemento_focado()

        if texto:
            await self.session.digitar(texto)
        if tecla:
            await self.session.apertar(tecla)

        if foco is None or not foco.editable:
            # Esc ou Tab sem campo e legitimo (fechar um modal, pular foco). Texto sem
            # campo quase sempre e o usuario achando que esta digitando num campo --
            # sem avisar, as letras somem e o passo simplesmente nao existe no teste.
            aviso = ("Nenhum campo em foco — o texto nao foi para campo nenhum. "
                     "Clique no campo na tela antes de digitar.") if texto else ""
            return Evento(ok=True, message="Tecla enviada — nenhum campo em foco, nada gravado.",
                          aviso=aviso)

        mudou_valor = bool(texto) or tecla in _APAGAM or tecla.startswith(("Control+", "Meta+"))
        gravou = False
        if mudou_valor:
            valor = await self.session.valor(foco)
            ultimo = self.gravacao.ultimo_passo()
            # Uma palavra digitada sao varias teclas; no teste ela e um preenchimento
            # so, com o valor final do campo.
            if ultimo is not None and ultimo.action == Action.FILL and _mesmo_alvo(ultimo, foco):
                ultimo.value = valor
            else:
                self._gravar(Action.FILL, foco, valor, foco.selector.to_code(), url,
                             f'preencher "{foco.name}"')
            gravou = True

        if tecla == "Enter":
            self._gravar(Action.PRESS, foco, "Enter", foco.selector.to_code(), url,
                         f'Enter em "{foco.name}"')
            gravou = True

        return Evento(ok=True, gravado=gravou, message=f'Digitando em "{foco.name}".',
                      selector_code=foco.selector.to_code())

    async def selecionar(self, valor: str) -> Evento:
        element = self._select_pendente
        self._select_pendente = None
        if element is None:
            return Evento(ok=False, message="Nao ha lista esperando uma escolha.")
        url = self.session.current_url
        codigo = element.selector.to_code()
        await self.session.escolher(element, valor)
        self._gravar(Action.SELECT, element, valor, codigo, url,
                     f'selecionar "{valor}" em "{element.name}"')
        return Evento(ok=True, gravado=True, message=f'Selecionei "{valor}" em "{element.name}"',
                      selector_code=codigo)

    async def validar(self, x: float, y: float) -> Evento:
        """Modo validar: o texto clicado vira um "esse texto tem que aparecer"."""
        url = self.session.current_url
        texto = await self.session.texto_em(x, y)
        if not texto:
            return Evento(ok=False, message="Nao achei texto nesse ponto.")
        # O texto acabou de ser lido da tela, mas a validacao do replay e get_by_text:
        # confere agora que ela encontra o que foi clicado. 2s bastam -- o texto esta
        # na tela neste instante; a espera longa e para o replay, nao para o record.
        if not await self.session.has_text(texto, timeout=2_000):
            return Evento(ok=False, message=f'O Playwright nao encontrou "{texto}" pelo texto — '
                                            "clique direto sobre a frase.")
        codigo = codigo_expect(texto)
        self._gravar(Action.EXPECT_TEXT, None, texto, codigo, url, f'validar "{texto}"')
        return Evento(ok=True, gravado=True, message=f'Vou validar: "{texto}"', selector_code=codigo)

    async def rolar(self, x: float, y: float, dx: float, dy: float) -> Evento:
        # Rolagem nao vira passo: o Playwright rola sozinho ate o elemento no replay.
        await self.session.rolar(x, y, dx, dy)
        return Evento(ok=True, message="")

    async def mover(self, x: float, y: float) -> Evento:
        # Hover tambem nao vira passo; e so para o que abre com o mouse em cima abrir.
        await self.session.mover(x, y)
        return Evento(ok=True, message="")
