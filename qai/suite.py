"""Gravar o que deu certo e transformar isso num teste que roda sozinho.

Cada passo bem-sucedido -- vindo do chat ou do record -- e anotado com o seletor que
o Playwright ja provou resolver naquele elemento: nao o palpite da LLM, o seletor
conferido contra o DOM vivo. O teste em construcao e uma lista de itens: passos soltos
e blocos (trechos reutilizaveis, ver blocos.py). Salvar o teste e despejar essa lista
num arquivo.

Rodar o teste e percorrer a lista de novo, e ai **nenhuma LLM e chamada**: nao ha
mais nada para interpretar, a decisao ja foi tomada e gravada. E por isso que a
re-execucao e deterministica e rapida -- e tambem por isso que ela nao se adapta:
se a pagina mudar de verdade, o passo falha em vez de inventar outro caminho.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .actions import codigo_expect, run_action, run_expect_text
from .blocos import carregar_bloco, salvar_bloco
from .browser import BrowserSession
from .config import ROOT
from .models import EDITABLE_ACTIONS, Action, Block, CommandResult, Item, Step, TestCase
from .textutil import slugify

PASTA = ROOT / "testes"


def _slug(nome: str) -> str:
    return slugify(nome, "teste")


def _caminho(slug: str) -> Path:
    return PASTA / f"{slug}.json"


# ---------- blocos dentro de um teste ----------

@dataclass
class PassoExpandido:
    """Um passo pronto para rodar, com o bloco de onde veio (se veio de um)."""

    step: Step | None       # None: o item apontava para um bloco que nao existe mais
    bloco: str = ""
    erro: str = ""


def expandir(items: list[Item]) -> list[PassoExpandido]:
    """Troca cada referencia a bloco pelos passos atuais do bloco.

    E aqui que "corrigir o bloco corrige todos os testes" acontece: o bloco e lido na
    hora de rodar, nao na hora de salvar o teste.
    """
    saida: list[PassoExpandido] = []
    for item in items:
        if item.kind == "step" and item.step is not None:
            saida.append(PassoExpandido(step=item.step))
            continue
        bloco = carregar_bloco(item.block)
        if bloco is None:
            saida.append(PassoExpandido(
                step=None, bloco=item.block,
                erro=f'O bloco "{item.block}" nao existe mais — foi excluido?',
            ))
            continue
        saida.extend(PassoExpandido(step=s, bloco=bloco.name) for s in bloco.steps)
    return saida


def url_inicial(items: list[Item]) -> str:
    """Onde o fluxo comeca: a pagina do primeiro passo, mesmo que ele esteja num bloco."""
    passos = expandir(items[:1])
    if passos and passos[0].step is not None:
        return passos[0].step.url
    return ""


class Gravacao:
    """O teste em construcao: passos e blocos, ainda nao salvos."""

    def __init__(self) -> None:
        self.items: list[Item] = []

    @property
    def url_inicial(self) -> str:
        return url_inicial(self.items)

    def registrar(self, state: dict, url_antes: str) -> None:
        """Anota um comando do chat que deu certo, direto do estado final do grafo.

        O estado ja tem tudo: a acao escolhida, o elemento resolvido e o valor
        recortado. E a URL vem de *antes* do passo rodar -- depois de um clique que
        navega, a pagina atual ja nao e mais o ponto de partida do passo.
        """
        action = state.get("action")
        if action is None:
            return

        element = state.get("element")
        resultado = state.get("result")
        self.adicionar(Step(
            action=action,
            text=state.get("text", ""),
            value=state.get("value") or "",
            selector=element.selector if element else None,
            element_name=element.name if element else "",
            element_form=element.form if element else "",
            code=resultado.selector_code if resultado else "",
            url=url_antes,
        ))

    def adicionar(self, step: Step) -> None:
        self.items.append(Item(kind="step", step=step))

    def ultimo_passo(self) -> Step | None:
        if self.items and self.items[-1].kind == "step":
            return self.items[-1].step
        return None

    # ---------- edicao ----------

    def _conferir(self, indice: int) -> Item:
        if not 0 <= indice < len(self.items):
            raise ValueError("Esse item nao existe mais — a lista mudou.")
        return self.items[indice]

    def remover(self, indice: int) -> None:
        self._conferir(indice)
        del self.items[indice]

    def mover(self, indice: int, para: int) -> None:
        item = self._conferir(indice)
        if not 0 <= para < len(self.items):
            raise ValueError("Nao da para mover para fora da lista.")
        del self.items[indice]
        self.items.insert(para, item)

    def editar(self, indice: int, valor: str) -> None:
        """Corrige o valor de um passo sem regravar -- o texto validado, o que foi
        digitado. E o que permite trocar um dado variavel por mascara (XXXX-X)."""
        item = self._conferir(indice)
        step = item.step
        if item.kind != "step" or step is None or step.action not in EDITABLE_ACTIONS:
            raise ValueError("Esse passo nao tem valor para editar.")
        step.value = valor
        if step.action == Action.EXPECT_TEXT:
            # O codigo mostrado inclui o texto; sem refazer, ele mentiria sobre o passo.
            step.code = codigo_expect(valor)

    def inserir_bloco(self, bloco: Block) -> None:
        self.items.append(Item(kind="block", block=bloco.slug))

    def agrupar(self, indices: list[int], nome: str, substituir: bool) -> Block:
        """Transforma passos soltos num bloco e poe o bloco no lugar deles."""
        escolhidos = sorted(set(indices))
        if not escolhidos:
            raise ValueError("Selecione ao menos um passo.")
        for i in escolhidos:
            item = self._conferir(i)
            if item.kind != "step":
                raise ValueError("Um bloco so pode ser feito de passos soltos, nao de outros blocos.")

        steps = [self.items[i].step for i in escolhidos]
        bloco = salvar_bloco(nome, [s for s in steps if s is not None], substituir)

        # O bloco ocupa a posicao do primeiro passo escolhido.
        primeiro = escolhidos[0]
        for i in reversed(escolhidos):
            del self.items[i]
        self.items.insert(primeiro, Item(kind="block", block=bloco.slug))
        return bloco

    def limpar(self) -> None:
        self.items = []


# ---------- arquivo ----------

def salvar(nome: str, gravacao: Gravacao) -> TestCase:
    """Escreve a gravacao atual em testes/<slug>.json. Mesmo nome sobrescreve."""
    if not gravacao.items:
        raise ValueError("Nada gravado ainda — grave passos pelo chat ou pelo record antes de salvar.")

    caso = TestCase(
        name=nome.strip() or "teste",
        slug=_slug(nome),
        created_at=datetime.now().isoformat(timespec="seconds"),
        url_inicial=gravacao.url_inicial,
        items=[item.model_copy(deep=True) for item in gravacao.items],
    )
    PASTA.mkdir(parents=True, exist_ok=True)
    _caminho(caso.slug).write_text(
        caso.model_dump_json(indent=2, exclude={"steps"}), encoding="utf-8",
    )
    return caso


def carregar(slug: str) -> TestCase | None:
    arquivo = _caminho(_slug(slug))
    if not arquivo.exists():
        return None
    try:
        return TestCase.model_validate_json(arquivo.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - arquivo mexido a mao e quebrado
        return None


def listar() -> list[TestCase]:
    if not PASTA.exists():
        return []
    casos = []
    for arquivo in sorted(PASTA.glob("*.json")):
        try:
            casos.append(TestCase.model_validate_json(arquivo.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - um arquivo torto nao derruba a lista inteira
            continue
    return casos


def excluir(slug: str) -> bool:
    """Apaga testes/<slug>.json. Os blocos que ele usava ficam: podem servir a outros."""
    arquivo = _caminho(_slug(slug))
    if not arquivo.exists():
        return False
    arquivo.unlink()
    return True


def testes_que_usam(slug: str) -> list[str]:
    """Nomes dos testes salvos que referenciam o bloco -- o que quebra se ele sumir."""
    return [c.name for c in listar() if any(i.kind == "block" and i.block == slug for i in c.items)]


# ---------- execucao ----------

async def rodar(session: BrowserSession, caso: TestCase) -> list[tuple[str, CommandResult]]:
    """Re-executa um teste salvo. Devolve (rotulo do passo, resultado).

    Para no primeiro passo que falha, pela mesma razao do chat: depois de um
    preenchimento que nao aconteceu, o clique seguinte so produziria um segundo erro
    sem sentido.
    """
    saida: list[tuple[str, CommandResult]] = []
    passos = expandir(caso.items)
    total = len(passos)

    session.active_form = ""
    session.last_element = None

    # Se o teste nao comeca abrindo a pagina, abrimos por ele.
    primeiro = passos[0].step if passos else None
    comeca_abrindo = primeiro is not None and primeiro.action == Action.GOTO
    if caso.url_inicial and not comeca_abrindo:
        abertura = await run_action(session, Action.GOTO, None, caso.url_inicial)
        saida.append((f"preparando: {caso.url_inicial}", abertura))
        if not abertura.ok:
            return saida

    for indice, passo in enumerate(passos):
        step = passo.step
        if step is None:
            resultado = CommandResult(ok=False, message=passo.erro)
            rotulo = f"bloco {passo.bloco}"
        else:
            if step.action == Action.EXPECT_TEXT:
                resultado = await run_expect_text(session, step.value)
            else:
                resultado = await run_action(session, step.action, step.to_element(), step.value)
            rotulo = f"{passo.bloco} › {step.label}" if passo.bloco else step.label

        saida.append((f"{indice + 1}/{total}: {rotulo}", resultado))

        if not resultado.ok:
            restantes = total - indice - 1
            if restantes:
                saida.append(("", CommandResult(
                    ok=False,
                    message=f"Parei aqui — {restantes} passo(s) seguinte(s) nao foram executados.",
                )))
            break

    return saida
