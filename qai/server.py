"""Servidor local do Qaí.

Uma sessao de browser, um grafo, uma pagina. O teste e montado de dois jeitos, que
podem se misturar: pelo chat (o usuario descreve em portugues e a LLM interpreta) ou
pelo record (o usuario clica e digita na tela embutida). Nos dois, o Playwright age na
mesma pagina e cada passo que da certo entra no teste em construcao, com o seletor
que provou funcionar.

Trechos do teste em construcao viram blocos reutilizaveis; o teste salvo roda de novo
sem a LLM no meio.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi import Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .actions import run_action
from .blocos import carregar_bloco, excluir_bloco, listar_blocos
from .browser import BrowserSession
from .commands import split_commands
from .config import configure_langsmith, settings
from .graph import build_graph
from .literals import find_url
from .models import EDITABLE_ACTIONS, Action, CommandResult, Step
from .record import Evento, Gravador
from .suite import Gravacao, carregar, excluir as excluir_teste, expandir, listar, rodar, salvar, testes_que_usam

# O frontend e um app React em frontend/; `npm run build` escreve o resultado aqui.
DIST_DIR = Path(__file__).resolve().parent / "web" / "dist"

app = FastAPI(title="Qaí")
# check_dir=False: sem build, o servidor ainda sobe e a rota "/" explica o que falta.
app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets", check_dir=False), name="assets")
session = BrowserSession()
graph = build_graph(session)
gravacao = Gravacao()
gravador = Gravador(session, gravacao)

# Chat, record e replay mexem na mesma pagina. Sem esta trava, uma tecla do record
# poderia cair no meio de um replay e digitar no campo errado. Um de cada vez.
trava = asyncio.Lock()


class Command(BaseModel):
    text: str


class Url(BaseModel):
    url: str


class Nome(BaseModel):
    nome: str


class Slug(BaseModel):
    slug: str


class Reply(BaseModel):
    ok: bool
    message: str
    action: str = ""
    selector_code: str = ""
    step: str = ""
    url: str = ""
    elements: list[str] = []


class PassoView(BaseModel):
    label: str
    action: str
    value: str = ""
    selector_code: str = ""
    editavel: bool = False


class ItemView(BaseModel):
    tipo: Literal["passo", "bloco"]
    passo: PassoView | None = None
    bloco_slug: str = ""
    bloco_nome: str = ""
    bloco_passos: list[PassoView] = []
    bloco_ausente: bool = False


class Gravado(BaseModel):
    url_inicial: str = ""
    itens: list[ItemView] = []
    total_passos: int = 0


class TesteSalvo(BaseModel):
    slug: str
    nome: str
    passos: int
    blocos: int
    criado_em: str


class BlocoView(BaseModel):
    slug: str
    nome: str
    criado_em: str
    url_inicial: str
    passos: list[PassoView]
    usado_em: list[str]


def _reply(result: CommandResult) -> Reply:
    return Reply(
        ok=result.ok,
        message=result.message,
        action=result.action.value if result.action else "",
        selector_code=result.selector_code,
        url=session.current_url,
        elements=[f"{e.describe()}" for e in session.elements],
    )


def _passo_view(step: Step) -> PassoView:
    return PassoView(
        label=step.label,
        action=step.action.value,
        value=step.value,
        selector_code=step.selector_code,
        editavel=step.action in EDITABLE_ACTIONS,
    )


@app.on_event("startup")
def _startup() -> None:
    configure_langsmith()


@app.get("/", response_model=None)
def index() -> FileResponse | HTMLResponse:
    pagina = DIST_DIR / "index.html"
    if not pagina.exists():
        return HTMLResponse(
            "<h1>Frontend nao compilado</h1>"
            "<p>Rode <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code> "
            "e recarregue a pagina.</p>",
            status_code=503,
        )
    return FileResponse(pagina)


@app.get("/api/estado")
def estado() -> Reply:
    return Reply(
        ok=session.is_open,
        message="Browser aberto." if session.is_open else "Nenhuma pagina aberta ainda.",
        url=session.current_url,
        elements=[e.describe() for e in session.elements],
    )


@app.post("/api/comando")
async def comando(command: Command) -> list[Reply]:
    """Uma mensagem pode conter varias ordens; cada uma vira um passo.

    A cadeia para no primeiro passo que nao der certo: continuar clicando depois de
    um preenchimento que falhou so produziria um segundo erro sem sentido.
    """
    text = command.text.strip()
    if not text:
        return [Reply(ok=False, message="Comando vazio.")]

    passos = split_commands(text)
    respostas: list[Reply] = []

    async with trava:
        # A LLM escolhe entre os elementos do inventario: se o record mexeu na pagina,
        # ele esta velho e precisa ser refeito antes da primeira pergunta.
        await session.garantir_inventario()
        for indice, passo in enumerate(passos):
            # Antes de executar: um clique que navega ja teria trocado a URL.
            url_antes = session.current_url
            try:
                final = await graph.ainvoke({"text": passo}, config={"run_name": "comando_qai"})
            except Exception as exc:  # noqa: BLE001 - a mensagem crua ajuda no chat
                resposta = Reply(ok=False, message=f"Falhou: {exc}", url=session.current_url)
            else:
                resultado = final["result"]
                resposta = _reply(resultado)
                # So o que deu certo entra no teste: um passo que falhou nao e um passo.
                if resultado.ok:
                    gravacao.registrar(final, url_antes)

            if len(passos) > 1:
                resposta.step = f"{indice + 1}/{len(passos)}: {passo}"
            respostas.append(resposta)

            if not resposta.ok:
                restantes = len(passos) - indice - 1
                if restantes:
                    respostas.append(Reply(
                        ok=False,
                        message=f"Parei aqui — {restantes} comando(s) seguinte(s) nao foram executados.",
                        url=session.current_url,
                    ))
                break

    return respostas


@app.post("/api/abrir")
async def abrir(alvo: Url) -> Reply:
    """Abre uma URL digitada no campo da tela inicial, sem passar pela LLM.

    Ali o usuario ja disse que e uma URL; perguntar ao modelo que acao e essa seria
    gastar uma chamada para ouvir a resposta que ja se sabe. O despacho e o mesmo
    run_action do replay, entao o passo gravado e identico ao de um "goto" do chat.
    """
    url = find_url(alvo.url.strip())
    if url is None:
        return Reply(ok=False, message=f'"{alvo.url}" nao parece uma URL.', url=session.current_url)

    async with trava:
        url_antes = session.current_url
        resultado = await run_action(session, Action.GOTO, None, url)
        if resultado.ok:
            gravacao.registrar(
                {"text": url, "action": Action.GOTO, "value": url, "result": resultado},
                url_antes,
            )
    return _reply(resultado)


# ---------- record ----------

class Ponto(BaseModel):
    x: float
    y: float
    modo: Literal["interagir", "validar"] = "interagir"


class Teclado(BaseModel):
    texto: str = ""
    tecla: str = ""


class Escolha(BaseModel):
    valor: str


class Rolagem(BaseModel):
    x: float
    y: float
    dx: float = 0
    dy: float = 0


class RecordReply(Evento):
    url: str = ""
    elements: list[str] = []


async def _gesto(acao) -> RecordReply:
    """Roda um gesto do record sob a trava e anexa o estado atual da pagina."""
    if not session.is_open:
        return RecordReply(ok=False, message="Abra uma pagina antes de gravar.")
    async with trava:
        try:
            evento: Evento = await acao()
        except Exception as exc:  # noqa: BLE001 - vira aviso na tela, nao stacktrace
            evento = Evento(ok=False, message=f"Falhou: {str(exc).strip().splitlines()[0]}")
    return RecordReply(
        **evento.model_dump(),
        url=session.current_url,
        elements=[e.describe() for e in session.elements],
    )


@app.post("/api/record/clique")
async def record_clique(p: Ponto) -> RecordReply:
    if p.modo == "validar":
        return await _gesto(lambda: gravador.validar(p.x, p.y))
    return await _gesto(lambda: gravador.clicar(p.x, p.y))


@app.post("/api/record/teclado")
async def record_teclado(t: Teclado) -> RecordReply:
    return await _gesto(lambda: gravador.teclado(t.texto, t.tecla))


@app.post("/api/record/selecionar")
async def record_selecionar(e: Escolha) -> RecordReply:
    return await _gesto(lambda: gravador.selecionar(e.valor))


@app.post("/api/record/rolar")
async def record_rolar(r: Rolagem) -> RecordReply:
    return await _gesto(lambda: gravador.rolar(r.x, r.y, r.dx, r.dy))


@app.post("/api/record/mover")
async def record_mover(p: Ponto) -> Response:
    """Hover. Fora da trava de proposito: chega varias vezes por segundo, nao grava
    nada, e esperar atras de um clique so faria o menu abrir atrasado."""
    if session.is_open:
        try:
            await gravador.mover(p.x, p.y)
        except Exception:  # noqa: BLE001 - pagina navegando; o proximo movimento resolve
            pass
    return Response(status_code=204)


@app.post("/api/inventario")
async def inventario() -> Reply:
    """Remapeia a pagina. O record nao faz isso a cada gesto; a tela pede ao parar."""
    if not session.is_open:
        return Reply(ok=False, message="Nenhuma pagina aberta.")
    async with trava:
        await session.snapshot()
    return Reply(ok=True, message="Inventario atualizado.", url=session.current_url,
                 elements=[e.describe() for e in session.elements])


# ---------- teste em construcao ----------

class Indice(BaseModel):
    indice: int


class Mover(BaseModel):
    indice: int
    para: int


class Edicao(BaseModel):
    indice: int
    valor: str


class Agrupar(BaseModel):
    indices: list[int]
    nome: str
    substituir: bool = False


@app.get("/api/gravacao")
def ver_gravacao() -> Gravado:
    itens: list[ItemView] = []
    for item in gravacao.items:
        if item.kind == "step" and item.step is not None:
            itens.append(ItemView(tipo="passo", passo=_passo_view(item.step)))
            continue
        bloco = carregar_bloco(item.block)
        itens.append(ItemView(
            tipo="bloco",
            bloco_slug=item.block,
            bloco_nome=bloco.name if bloco else item.block,
            bloco_passos=[_passo_view(s) for s in bloco.steps] if bloco else [],
            bloco_ausente=bloco is None,
        ))
    return Gravado(
        url_inicial=gravacao.url_inicial,
        itens=itens,
        total_passos=len(expandir(gravacao.items)),
    )


def _editar(operacao, mensagem: str) -> Reply:
    try:
        operacao()
    except ValueError as exc:
        return Reply(ok=False, message=str(exc), url=session.current_url)
    return Reply(ok=True, message=mensagem, url=session.current_url)


@app.post("/api/gravacao/limpar")
def limpar_gravacao() -> Reply:
    gravacao.limpar()
    return Reply(ok=True, message="Gravacao descartada.", url=session.current_url)


@app.post("/api/gravacao/remover")
def remover_item(alvo: Indice) -> Reply:
    return _editar(lambda: gravacao.remover(alvo.indice), "Item removido.")


@app.post("/api/gravacao/mover")
def mover_item(alvo: Mover) -> Reply:
    return _editar(lambda: gravacao.mover(alvo.indice, alvo.para), "Item movido.")


@app.post("/api/gravacao/editar")
def editar_item(alvo: Edicao) -> Reply:
    return _editar(lambda: gravacao.editar(alvo.indice, alvo.valor), "Valor atualizado.")


@app.post("/api/gravacao/inserir-bloco")
def inserir_bloco(alvo: Slug) -> Reply:
    bloco = carregar_bloco(alvo.slug)
    if bloco is None:
        return Reply(ok=False, message="Nao achei esse bloco.")
    gravacao.inserir_bloco(bloco)
    return Reply(ok=True, message=f'Bloco "{bloco.name}" adicionado ao teste.', url=session.current_url)


@app.post("/api/gravacao/agrupar")
def agrupar(alvo: Agrupar) -> Reply:
    try:
        bloco = gravacao.agrupar(alvo.indices, alvo.nome, alvo.substituir)
    except ValueError as exc:
        return Reply(ok=False, message=str(exc))
    return Reply(
        ok=True,
        message=f'Bloco "{bloco.name}" criado com {len(bloco.steps)} passo(s) em blocos/{bloco.slug}.json',
        url=session.current_url,
    )


# ---------- blocos ----------

@app.get("/api/blocos")
def blocos() -> list[BlocoView]:
    return [
        BlocoView(
            slug=b.slug,
            nome=b.name,
            criado_em=b.created_at,
            url_inicial=b.url_inicial,
            passos=[_passo_view(s) for s in b.steps],
            usado_em=testes_que_usam(b.slug),
        )
        for b in listar_blocos()
    ]


@app.post("/api/blocos/excluir")
def excluir(alvo: Slug) -> Reply:
    if not excluir_bloco(alvo.slug):
        return Reply(ok=False, message="Nao achei esse bloco.")
    return Reply(ok=True, message="Bloco excluido.")


# ---------- testes salvos ----------

@app.get("/api/testes")
def testes() -> list[TesteSalvo]:
    return [
        TesteSalvo(
            slug=c.slug,
            nome=c.name,
            passos=len(expandir(c.items)),
            blocos=sum(1 for i in c.items if i.kind == "block"),
            criado_em=c.created_at,
        )
        for c in listar()
    ]


@app.post("/api/testes")
def salvar_teste(alvo: Nome) -> Reply:
    try:
        caso = salvar(alvo.nome, gravacao)
    except ValueError as exc:
        return Reply(ok=False, message=str(exc))
    return Reply(
        ok=True,
        message=f'Teste "{caso.name}" salvo com {len(caso.items)} item(ns) em testes/{caso.slug}.json',
        url=session.current_url,
    )


@app.post("/api/testes/excluir")
def apagar_teste(alvo: Slug) -> Reply:
    caso = carregar(alvo.slug)
    if caso is None or not excluir_teste(alvo.slug):
        return Reply(ok=False, message="Nao achei esse teste salvo.")
    return Reply(ok=True, message=f'Teste "{caso.name}" apagado.')


@app.post("/api/testes/rodar")
async def rodar_teste(alvo: Slug) -> list[Reply]:
    """Re-executa um teste salvo. Sem LLM: os seletores ja estao decididos."""
    caso = carregar(alvo.slug)
    if caso is None:
        return [Reply(ok=False, message="Nao achei esse teste salvo.")]

    async with trava:
        resultados = await rodar(session, caso)

    respostas: list[Reply] = []
    for rotulo, resultado in resultados:
        resposta = _reply(resultado)
        resposta.step = rotulo
        respostas.append(resposta)
    return respostas


@app.get("/api/tela")
async def tela(n: int = -2) -> Response:
    """Quadro atual do browser. A pagina pede este endpoint a cada ~100ms.

    `n` e o numero do quadro que a tela ja mostra: se ainda e o atual, a resposta e
    304 e nada trafega. 204 significa uma coisa so -- nao ha pagina aberta.
    """
    atual = await session.quadro()
    if atual is None:
        return Response(status_code=204)
    numero, imagem = atual
    if imagem is None or (numero == n and numero >= 0):
        return Response(status_code=304)
    return Response(content=imagem, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store", "X-Quadro": str(numero)})


@app.post("/api/encerrar")
async def encerrar() -> Reply:
    async with trava:
        await session.close()
    return Reply(ok=True, message="Browser fechado.")


def serve() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
