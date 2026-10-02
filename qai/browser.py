"""Sessao de browser viva, compartilhada entre os comandos do chat.

O browser abre uma vez, na frente do usuario, e fica aberto. Cada comando age sobre
a mesma pagina e, logo depois, o inventario e remontado -- e assim que o agente
enxerga o que mudou (um modal que apareceu, um campo novo, outra tela).

A leitura da pagina nao confia no palpite da LLM: cada elemento e carimbado com um
atributo temporario e o seletor candidato so e aceito se, testado contra a pagina
viva, resolver para exatamente aquele elemento.
"""

from __future__ import annotations

import re
import asyncio
import base64
from dataclasses import dataclass, field

from playwright.async_api import Locator, Page, async_playwright

from .config import settings
from .literals import to_pattern
from .models import PageElement, Selector

STAMP = "data-qai-id"

# Esperar um tempo fixo depois de cada acao e uma corrida perdida: medimos o BugBank
# trocando de tela entre 101ms e 376ms depois do mesmo clique. Amostrar a pagina de
# tempos em tempos tambem falha, porque uma pausa entre dois renders parece "estavel".
#
# O sinal confiavel e o proprio navegador avisando: um MutationObserver marca a hora
# da ultima alteracao no DOM, e so consideramos a pagina pronta quando fizer um tempo
# que nada muda.
SETTLE_PASSO_MS = 100     # intervalo entre consultas
SETTLE_MINIMO_MS = 400    # nunca decide antes disso
SETTLE_QUIETO_MS = 500    # tempo sem nenhuma mutacao para considerar pronta
SETTLE_LIMITE_MS = 5000   # teto, para pagina que nunca para (spinner, carrossel)

# Instala o observador uma vez por documento e devolve ha quantos ms nada muda.
# Depois de uma navegacao o window e novo, entao ele se reinstala sozinho e o contador
# volta a zero -- que e exatamente o certo: acabou de mudar tudo.
_MUTACAO_JS = """
() => {
  if (window.__qaiMut === undefined) {
    window.__qaiMut = Date.now();
    const obs = new MutationObserver(() => { window.__qaiMut = Date.now(); });
    obs.observe(document.documentElement, {
      childList: true, subtree: true, attributes: true, characterData: true,
    });
  }
  return Date.now() - window.__qaiMut;
}
"""

# Como descrever um elemento para montar os seletores candidatos. Compartilhado pela
# leitura da pagina inteira (snapshot) e pelo record, que descreve so o elemento
# clicado: os dois precisam chegar ao mesmo seletor para o mesmo elemento.
_DESCREVER_JS = """
  const first = (s) => (s || '').split('\\n')[0].trim().slice(0, 60);

  const descrever = (el) => {
    const type = (el.getAttribute('type') || '').toLowerCase();
    let label = '';
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) label = first(l.innerText);
    }
    if (!label && el.closest('label')) label = first(el.closest('label').innerText);
    if (!label) label = first(el.getAttribute('aria-label'));

    const tag = el.tagName.toLowerCase();
    const isBotao = tag === 'button' || type === 'submit' || type === 'button';
    let role = el.getAttribute('role') || '';
    if (!role) {
      if (isBotao) role = 'button';
      else if (tag === 'a') role = el.getAttribute('href') ? 'link' : 'button';
      else if (tag === 'select') role = 'combobox';
      else if (type === 'checkbox') role = 'checkbox';
      else if (type === 'radio') role = 'radio';
      else if (tag === 'input' || tag === 'textarea') role = 'textbox';
      else role = 'button';  // div/span clicavel: age como botao
    }

    // O formulario a que pertence, nomeado pelo texto do seu botao de submit.
    // E o que distingue o campo "e-mail" do login do campo "e-mail" do cadastro.
    let form = '';
    const f = el.closest('form');
    if (f) {
      const submit = f.querySelector('button[type="submit"]')
        || f.querySelector('input[type="submit"]')
        || f.querySelector('button');
      form = first(submit ? (submit.innerText || submit.value) : '');
    }

    // Da para digitar aqui? Vale o tipo do elemento, nao o papel ARIA: a caixa de
    // busca do Google e uma <textarea> com role="combobox", e continua sendo um
    // campo de texto.
    const naoEditaveis = ['checkbox', 'radio', 'file', 'range', 'color'];
    const editavel = tag === 'textarea'
      || (tag === 'input' && !isBotao && naoEditaveis.indexOf(type) === -1);

    return {
      editable: editavel,
      tag: tag,
      role: role,
      label: label,
      // el.value so serve de rotulo em botao. Em campo de texto, value e o que o
      // usuario acabou de digitar -- usar isso como nome renomearia o campo
      // "Informe sua senha" para "Teste@123" depois do primeiro preenchimento.
      text: first(el.innerText || (isBotao ? el.value : '') || ''),
      dom_id: el.id || '',
      dom_name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      input_type: type,
      form: form,
    };
  };
"""

_COLLECT_JS = """
(stamp) => {
""" + _DESCREVER_JS + """
  const out = [];
  let n = 0;

  const SEMANTICOS = 'input, button, select, textarea, a[href], [role="button"]';

  // Alem dos elementos semanticos, pegamos os que apenas se comportam como botao:
  // div/span/p com cursor:pointer. O modal do BugBank fecha num elemento desses --
  // "Fechar" nao e um <button>, entao sem isto o agente simplesmente nao o enxerga.
  // Inclui 'a' porque uma ancora sem href nao casa com a[href] dos semanticos -- e e
  // exatamente assim que o BugBank faz o "Fechar" do modal: <a id="btnCloseModal">.
  const soltos = Array.from(document.querySelectorAll('div, span, p, li, a')).filter((el) => {
    if (el.matches(SEMANTICOS)) return false;   // ja entrou pela porta da frente
    if (getComputedStyle(el).cursor !== 'pointer') return false;
    if (el.querySelector(SEMANTICOS)) return false;          // tem um de verdade dentro
    const texto = (el.innerText || '').trim();
    if (texto.length > 40) return false;
    // Sem texto ainda serve, desde que exista um identificador: os cards da home do
    // BugBank sao <a> vazios, com o rotulo so no id (id="btn-TRANSFERENCIA").
    if (!texto && !el.id && !el.getAttribute('aria-label')) return false;
    // Prefere o elemento mais interno: se um filho tambem parece clicavel, e dele a vez.
    return !Array.from(el.querySelectorAll('*')).some(
      (filho) => getComputedStyle(filho).cursor === 'pointer' && (filho.innerText || '').trim()
    );
  });

  [].concat(Array.from(document.querySelectorAll(SEMANTICOS)), soltos)
    .forEach((el) => {
      const type = (el.getAttribute('type') || '').toLowerCase();
      if (type === 'hidden') return;

      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (rect.width < 2 || rect.height < 2) return;
      if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return;

      // Visivel de verdade: o elemento precisa ser o que esta por cima no proprio centro.
      // O BugBank troca entre login e cadastro virando um cartao 3D -- os campos da face
      // escondida continuam com tamanho e visibility:visible, e so este teste os separa.
      // De quebra, isto exclui o que estiver atras de um modal, que e justamente o que
      // nao da para clicar.
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      if (cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight) {
        const topo = document.elementFromPoint(cx, cy);
        if (topo && topo !== el && !el.contains(topo)) return;
      }

      const descricao = descrever(el);
      const id = 'E' + (++n);
      el.setAttribute(stamp, id);
      descricao.id = id;
      out.push(descricao);
    });

  return out;
}
"""

# Record: o elemento sob o cursor, no instante do clique -- antes de clicar, porque
# depois o clique pode ter fechado o modal ou trocado de tela, e ai nao ha mais o que
# descrever. Carimba com um id que vem do Python (unico mesmo entre navegacoes).
_ALVO_JS = """
({ x, y, attr, id }) => {
""" + _DESCREVER_JS + """
  let el = document.elementFromPoint(x, y);
  if (!el) return null;
  // Clicar no rotulo e clicar no campo dele: quem recebe a acao e o controle.
  const rotulo = el.closest('label');
  if (rotulo && rotulo.control) el = rotulo.control;

  const INTERATIVOS = 'input, select, textarea, button, a, summary, [role="button"], '
    + '[role="link"], [role="checkbox"], [role="radio"], [role="tab"], [role="menuitem"], '
    + '[role="option"], [role="switch"]';
  let alvo = el.closest(INTERATIVOS);
  if (!alvo) {
    // Sem semantica: o que tem cara de clicavel. cursor:pointer e herdado pelos
    // filhos, entao vale o primeiro ancestral com pointer que tenha um nome -- texto
    // curto ou id --, a mesma regra dos elementos "soltos" do snapshot.
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (getComputedStyle(n).cursor !== 'pointer') continue;
      const texto = (n.innerText || '').trim();
      if ((texto && texto.length <= 40) || n.id || n.getAttribute('aria-label')) { alvo = n; break; }
    }
  }
  if (!alvo) return { interativo: false };

  alvo.setAttribute(attr, id);
  const d = descrever(alvo);
  d.id = id;
  d.interativo = true;
  if (d.tag === 'select') {
    d.opcoes = Array.from(alvo.options).map((o) => ({ valor: o.value, texto: o.text.trim() }));
  }
  return d;
}
"""

# Record: o campo em que o teclado esta. Reaproveita o carimbo se ja houver um, para o
# Python achar o seletor no cache e nao resolver tudo de novo a cada tecla.
_FOCO_JS = """
({ attr, id }) => {
""" + _DESCREVER_JS + """
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  const existente = el.getAttribute(attr);
  if (!existente) el.setAttribute(attr, id);
  const d = descrever(el);
  d.id = existente || id;
  return d;
}
"""

# Record, modo validar: o texto em que o usuario clicou. Vale o menor elemento com
# texto PROPRIO no ponto -- clicar no espaco de um container juntava os textos de
# varios filhos ("E-mail Senha Acessar Registrar"), frase que nao existe em elemento
# nenhum, e get_by_text esperava 10s para concluir isso. Espacos e quebras de linha
# viram um espaco so, que e como get_by_text compara.
_TEXTO_JS = """
({ x, y }) => {
  const INTERATIVOS = 'a, button, input, select, textarea, script, style';
  for (let n = document.elementFromPoint(x, y); n && n !== document.body; n = n.parentElement) {
    const proprio = Array.from(n.childNodes).some((c) => c.nodeType === 3 && c.textContent.trim());
    if (!proprio) continue;
    let texto = n.innerText || '';
    // Mensagem com botao dentro ("You logged in! ×"): o × de fechar nao e parte do que
    // se quer validar. Numa copia sem os controles, <br> vira espaco -- sem isso as
    // duas linhas do modal do BugBank grudariam ("invalido.Tente").
    if (n.querySelector(INTERATIVOS)) {
      const copia = n.cloneNode(true);
      copia.querySelectorAll(INTERATIVOS).forEach((e) => e.remove());
      copia.querySelectorAll('br').forEach((e) => e.replaceWith(' '));
      texto = copia.textContent || '';
    }
    texto = texto.replace(/\\s+/g, ' ').trim();
    if (texto) return texto.length > 200 ? texto.slice(0, 200).replace(/\\s+\\S*$/, '') : texto;
  }
  return '';
}
"""

REC_STAMP = "data-qai-rec"


@dataclass
class Alvo:
    """O que estava sob o cursor num clique do record."""

    elemento: PageElement | None
    tag: str = ""
    opcoes: list[dict] = field(default_factory=list)


def _nome_do_id(dom_id: str) -> str:
    """'btn-TRANSFERENCIA' -> 'TRANSFERENCIA'.

    Muita SPA nao poe texto nem aria-label no elemento clicavel e deixa o rotulo so
    no id. Sem isto, os cards da home do BugBank entram no inventario sem nome, e a
    LLM nao tem como escolher entre eles.
    """
    limpo = re.sub(r"^(?:btn|button)[-_]?", "", dom_id or "", flags=re.IGNORECASE)
    return re.sub(r"[-_]+", " ", limpo).strip()


def _candidates(raw: dict, *, scoped: bool) -> list[Selector]:
    """Seletores candidatos, do mais semantico para o mais estrutural."""
    form = raw["form"] if scoped else ""
    if scoped and not form:
        return []

    out: list[Selector] = []
    if raw["label"]:
        out.append(Selector(kind="label", value=raw["label"], form=form))
    if raw["role"] and raw["text"]:
        out.append(Selector(kind="role", value=raw["role"], name=raw["text"], form=form))
    if raw["placeholder"]:
        out.append(Selector(kind="placeholder", value=raw["placeholder"], form=form))
    if raw["dom_id"] and not scoped:
        out.append(Selector(kind="css", value="#" + raw["dom_id"]))
    if raw["dom_name"]:
        out.append(Selector(kind="css", value='[name="' + raw["dom_name"] + '"]', form=form))
    if raw["text"]:
        # Ultimo recurso semantico: casar pelo texto visivel. E o unico que funciona em
        # elemento clicavel sem semantica -- o "Fechar" do modal do BugBank nao e um
        # <button>, entao get_by_role nao o encontra.
        out.append(Selector(kind="text", value=raw["text"], form=form))
    if raw["role"] and raw["text"]:
        # Nome acessivel com sobra: <button><i class="fa fa-sign-in"> Login</i></button>
        # se chama " Login" (o glifo do icone entra no nome). Sem exact, casa por
        # trecho -- e o que o proprio codegen do Playwright gera. Vem depois dos exatos
        # porque "Login" tambem casaria "Login com Google"; a verificacao de unicidade
        # descarta esse caso.
        out.append(Selector(kind="role", value=raw["role"], name=raw["text"], form=form, exact=False))
    if raw["text"] and raw.get("tag"):
        # O texto mora num filho (o <i> do icone): get_by_text acha o filho, nao o botao.
        # :has-text mira o elemento que CONTEM o texto.
        texto = raw["text"].replace("\\", "\\\\").replace('"', '\\"')
        out.append(Selector(kind="css", value=f'{raw["tag"]}:has-text("{texto}")', form=form))
    return out


def _elemento(raw: dict, selector: Selector) -> PageElement:
    return PageElement(
        element_id=raw["id"],
        role=raw["role"],
        name=(raw["label"] or raw["text"] or raw["placeholder"]
              or _nome_do_id(raw["dom_id"]) or raw["dom_name"]),
        input_type=raw["input_type"],
        editable=raw.get("editable", False),
        form=raw["form"],
        selector=selector,
    )


class BrowserSession:
    """Um browser aberto, uma pagina, e o inventario mais recente dela."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page: Page | None = None
        self.elements: list[PageElement] = []
        # Formulario com que o usuario esta trabalhando, para desempatar campos repetidos.
        self.active_form: str = ""
        # Ultimo elemento em que o agente mexeu. E a unica memoria de conversa que
        # existe: permite "apague isso" se referir ao campo que acabou de ser preenchido.
        self.last_element: PageElement | None = None
        # Record: contador dos carimbos e os elementos ja resolvidos, por carimbo.
        self._rec_n = 0
        self._rec_cache: dict[str, PageElement] = {}
        # O record age sem remapear a pagina (custava ate 4s por clique). O inventario
        # fica marcado como velho e e refeito quando alguem precisar dele de novo.
        self.inventario_sujo = False
        # Transmissao da tela: o Chromium empurra um quadro a cada repintura. O numero
        # nunca volta a zero, nem entre sessoes -- a tela usa ele para saber se o quadro
        # que ja tem ainda e o atual.
        self._quadro: bytes | None = None
        self._quadro_n = 0

    # ---------- ciclo de vida ----------

    @property
    def is_open(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    @property
    def current_url(self) -> str:
        return self._page.url if self.is_open else ""

    async def _ensure_page(self) -> Page:
        if self.is_open:
            return self._page  # type: ignore[return-value]
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=settings.headless)
        context = await self._browser.new_context(viewport={"width": 1280, "height": 800})
        self._page = await context.new_page()
        await self._transmitir(self._page)
        return self._page

    async def _transmitir(self, page: Page) -> None:
        """Liga o screencast do Chromium: cada repintura vira um quadro guardado aqui.

        Tirar um screenshot a cada pedido da tela custava 30ms e so dava 3 quadros por
        segundo; com o screencast o quadro ja esta pronto quando a tela pede, e so muda
        quando a pagina muda de fato. Se nao ligar, screenshot() continua servindo.
        """
        try:
            cdp = await page.context.new_cdp_session(page)
        except Exception:  # noqa: BLE001 - sem CDP, fica o screenshot
            return

        async def confirmar(sessao: int) -> None:
            try:
                await cdp.send("Page.screencastFrameAck", {"sessionId": sessao})
            except Exception:  # noqa: BLE001 - pagina fechando
                pass

        def quadro(params: dict) -> None:
            self._quadro = base64.b64decode(params["data"])
            self._quadro_n += 1
            # Sem o ack o Chromium para de mandar quadros.
            asyncio.ensure_future(confirmar(params["sessionId"]))

        cdp.on("Page.screencastFrame", quadro)
        try:
            await cdp.send("Page.startScreencast", {
                "format": "jpeg", "quality": 60, "maxWidth": 1280, "maxHeight": 800, "everyNthFrame": 1,
            })
        except Exception:  # noqa: BLE001
            return

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._playwright = self._browser = self._page = None
        self.elements = []
        self.active_form = ""
        self.last_element = None
        self._rec_cache = {}
        self.inventario_sujo = False
        self._quadro = None

    # ---------- leitura da pagina ----------

    def locator(self, element: PageElement) -> Locator:
        page = self._page
        assert page is not None
        selector = element.selector
        root: Page | Locator = page
        if selector.form:
            root = page.locator('form:has(button:text-is("' + selector.form + '"))')

        if selector.kind == "label":
            found = root.get_by_label(selector.value, exact=True)
        elif selector.kind == "role":
            found = root.get_by_role(selector.value, name=selector.name, exact=selector.exact)  # type: ignore[arg-type]
        elif selector.kind == "placeholder":
            found = root.get_by_placeholder(selector.value, exact=True)
        elif selector.kind == "text":
            found = root.get_by_text(selector.value, exact=True)
        else:
            found = root.locator(selector.value)

        return found if selector.nth is None else found.nth(selector.nth)

    async def _resolves_uniquely(self, selector: Selector, stamp_id: str, attr: str = STAMP) -> bool:
        probe = self.locator(PageElement(element_id=stamp_id, selector=selector))
        try:
            if await probe.count() != 1:
                return False
            return await probe.first.get_attribute(attr, timeout=1000) == stamp_id
        except Exception:  # noqa: BLE001 - candidato invalido e so um candidato a menos
            return False

    async def _resolve(self, raw: dict, attr: str = STAMP) -> Selector | None:
        """O primeiro seletor que resolve, sozinho, exatamente este elemento.

        `attr` e o carimbo que identifica o elemento: o do snapshot ou o do record.
        Sao atributos diferentes para um nao apagar o outro quando os dois rodam.
        """
        # 1. Sem escopo. 2. Ancorado no formulario, se o de cima ficou ambiguo.
        for scoped in (False, True):
            for candidate in _candidates(raw, scoped=scoped):
                if await self._resolves_uniquely(candidate, raw["id"], attr):
                    return candidate

        # 3. Ultimo recurso: o seletor casa varios, entao fixamos a posicao. Feio, mas
        # melhor que descartar o elemento -- um elemento fora do inventario e um
        # elemento que o agente jura nao existir.
        for candidate in _candidates(raw, scoped=False):
            try:
                total = await self.locator(PageElement(element_id=raw["id"], selector=candidate)).count()
            except Exception:  # noqa: BLE001
                continue
            for indice in range(min(total, 10)):
                posicional = candidate.model_copy(update={"nth": indice})
                if await self._resolves_uniquely(posicional, raw["id"], attr):
                    return posicional
        return None

    async def snapshot(self) -> list[PageElement]:
        """Rele a pagina e devolve os elementos com seletor unico verificado."""
        page = await self._ensure_page()
        raw_elements = await page.evaluate(_COLLECT_JS, STAMP)

        found: list[PageElement] = []
        for raw in raw_elements:
            selector = await self._resolve(raw)
            if selector is not None:
                found.append(_elemento(raw, selector))

        self.elements = found
        self.inventario_sujo = False
        return found

    async def garantir_inventario(self) -> None:
        """Refaz o inventario se o record mexeu na pagina desde o ultimo snapshot."""
        if self.is_open and self.inventario_sujo:
            await self.snapshot()

    # ---------- record ----------
    #
    # No record o usuario age pela tela embutida: o clique chega como coordenada e o
    # teclado como texto. O elemento e identificado e o seletor verificado ANTES da
    # acao, com o mesmo _resolve do snapshot -- entao o passo gravado usa um seletor
    # que ja provou, na pagina viva, apontar para exatamente aquele elemento.

    def _proximo_rec(self) -> str:
        self._rec_n += 1
        return f"R{self._rec_n}"

    async def _avaliar(self, script: str, arg: dict):
        """evaluate que sobrevive a uma navegacao em andamento.

        O record nao espera a pagina assentar depois de um clique; se o proximo gesto
        chega enquanto a tela troca, o documento antigo ja morreu. Espera o novo
        carregar e tenta uma vez mais.
        """
        page = await self._ensure_page()
        try:
            return await page.evaluate(script, arg)
        except Exception:  # noqa: BLE001 - "Execution context was destroyed"
            await page.wait_for_load_state("domcontentloaded", timeout=10_000)
            return await page.evaluate(script, arg)

    async def elemento_em(self, x: float, y: float) -> Alvo | None:
        """O elemento interativo no ponto (x, y) da pagina, com seletor verificado."""
        raw = await self._avaliar(_ALVO_JS, {"x": x, "y": y, "attr": REC_STAMP, "id": self._proximo_rec()})
        if raw is None:
            return None
        if not raw.get("interativo"):
            return Alvo(elemento=None)
        selector = await self._resolve(raw, attr=REC_STAMP)
        elemento = _elemento(raw, selector) if selector else None
        if elemento:
            self._rec_cache[raw["id"]] = elemento
        return Alvo(elemento=elemento, tag=raw["tag"], opcoes=raw.get("opcoes") or [])

    async def elemento_focado(self) -> PageElement | None:
        """O campo que esta com o foco do teclado, com seletor verificado."""
        raw = await self._avaliar(_FOCO_JS, {"attr": REC_STAMP, "id": self._proximo_rec()})
        if raw is None:
            return None
        if raw["id"] in self._rec_cache:
            return self._rec_cache[raw["id"]]
        selector = await self._resolve(raw, attr=REC_STAMP)
        if selector is None:
            return None
        elemento = _elemento(raw, selector)
        self._rec_cache[raw["id"]] = elemento
        return elemento

    async def texto_em(self, x: float, y: float) -> str:
        return await self._avaliar(_TEXTO_JS, {"x": x, "y": y})

    # Os gestos abaixo NAO esperam a pagina assentar nem remapeiam o inventario: no
    # record o usuario esta olhando a tela e ja reage ao que ve. Esperar custava de
    # meio segundo a 4 segundos por clique, e e isso que fazia o record parecer travado.

    async def clicar_em(self, x: float, y: float) -> None:
        """Clica onde o usuario clicou -- o gesto real, sem esperas."""
        page = await self._ensure_page()
        await page.mouse.click(x, y)
        self.inventario_sujo = True

    async def clicavel(self, element: PageElement) -> bool:
        """O replay vai conseguir clicar neste elemento pelo seletor?

        trial=True faz todas as verificacoes do clique de verdade (visivel, estavel,
        nada por cima) sem clicar. E a prova de que o passo gravado se repete, em
        ~20ms -- em vez de clicar pelo seletor e ficar ate 15s preso num elemento coberto.
        """
        try:
            await self.locator(element).click(trial=True, timeout=1_000)
            return True
        except Exception:  # noqa: BLE001 - coberto, invisivel, instavel
            return False

    async def mover(self, x: float, y: float) -> None:
        """Movimento do mouse: sem ele, menu que abre no hover nunca abre."""
        page = await self._ensure_page()
        await page.mouse.move(x, y)

    async def digitar(self, texto: str) -> None:
        page = await self._ensure_page()
        await page.keyboard.type(texto)
        self.inventario_sujo = True

    async def apertar(self, tecla: str) -> None:
        page = await self._ensure_page()
        await page.keyboard.press(tecla)
        self.inventario_sujo = True

    async def escolher(self, element: PageElement, valor: str) -> None:
        await self.locator(element).select_option(valor, timeout=5_000)
        self.inventario_sujo = True

    async def rolar(self, x: float, y: float, dx: float, dy: float) -> None:
        page = await self._ensure_page()
        await page.mouse.move(x, y)
        await page.mouse.wheel(dx, dy)

    async def valor(self, element: PageElement) -> str:
        return await self.locator(element).input_value(timeout=2_000)

    # ---------- acoes ----------

    async def goto(self, url: str) -> None:
        page = await self._ensure_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await self._settle()  # SPA terminar de montar

    async def fill(self, element: PageElement, value: str) -> None:
        await self.locator(element).fill(value, timeout=15_000)
        await self._settle()

    async def clear(self, element: PageElement) -> None:
        await self.locator(element).fill("", timeout=15_000)
        await self._settle()

    async def click(self, element: PageElement) -> None:
        await self.locator(element).click(timeout=15_000)
        await self._settle()

    async def select(self, element: PageElement, value: str) -> None:
        await self.locator(element).select_option(value, timeout=15_000)
        await self._settle()

    async def press(self, element: PageElement, key: str) -> None:
        await self.locator(element).press(key, timeout=15_000)
        await self._settle()

    async def is_visible(self, element: PageElement) -> bool:
        try:
            return await self.locator(element).is_visible(timeout=5_000)
        except Exception:  # noqa: BLE001
            return False

    async def has_text(self, text: str, timeout: int = 10_000) -> bool:
        """Valida que um texto esta visivel na tela.

        get_by_text normaliza espacos em branco, entao casa mesmo quando a aplicacao
        quebra a mensagem em varias linhas -- o que o BugBank faz no modal de erro.
        """
        page = await self._ensure_page()
        # Texto com mascara ("A conta XXXX-X foi criada") vira regex; sem mascara,
        # segue a comparacao literal de sempre.
        padrao = to_pattern(text)
        alvo = padrao if padrao is not None else text
        try:
            await page.get_by_text(alvo).first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:  # noqa: BLE001 - nao achar o texto e um resultado, nao um erro
            return False

    async def quadro(self) -> tuple[int, bytes | None] | None:
        """(numero, jpeg) do quadro mais recente; None so quando nao ha pagina aberta.

        Antes do primeiro quadro do screencast (ou se ele nao ligou), cai no screenshot
        com numero -1, que nunca coincide com o da tela e por isso sempre e enviado.
        Screenshot que falha no meio de uma navegacao devolve jpeg None: "mantenha o
        que tem". Responder "nao ha pagina" ali fazia a tela piscar para o inicio e
        derrubava o foco do teclado no meio do record.
        """
        if not self.is_open:
            return None
        if self._quadro is not None:
            return self._quadro_n, self._quadro
        return -1, await self.screenshot()

    async def screenshot(self) -> bytes | None:
        """Quadro atual da pagina, para o chat mostrar o que esta acontecendo."""
        if not self.is_open:
            return None
        try:
            return await self._page.screenshot(type="jpeg", quality=55, timeout=5_000)
        except Exception:  # noqa: BLE001 - durante navegacao a captura falha; o chat
            return None    # simplesmente mantem o quadro anterior

    async def _settle(self) -> None:
        """Espera o DOM parar de mudar, em vez de apostar num tempo fixo."""
        page = self._page
        if page is None:
            return

        gasto = 0
        while gasto < SETTLE_LIMITE_MS:
            try:
                quieto_ha = await page.evaluate(_MUTACAO_JS)
            except Exception:  # noqa: BLE001 - navegando; ainda nao esta pronta
                quieto_ha = 0

            if gasto >= SETTLE_MINIMO_MS and quieto_ha >= SETTLE_QUIETO_MS:
                return

            await page.wait_for_timeout(SETTLE_PASSO_MS)
            gasto += SETTLE_PASSO_MS
