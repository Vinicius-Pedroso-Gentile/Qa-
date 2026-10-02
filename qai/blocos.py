"""Blocos: trechos de teste com nome, reutilizaveis entre testes.

Um bloco e um pedaco de fluxo que se repete -- "Login", "Cadastrar usuario". Ele e
feito a partir de passos ja gravados (pelo chat ou pelo record), entao cada passo ja
tem o seletor verificado; o bloco so da um nome a sequencia.

Os testes guardam a referencia ao bloco, nao uma copia dos passos. Quando a tela de
login mudar, regrava-se o bloco "Login" uma vez e todo teste que o usa passa a rodar
a versao nova.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import ROOT
from .models import Block, Step
from .textutil import slugify

PASTA = ROOT / "blocos"


def _caminho(slug: str) -> Path:
    return PASTA / f"{slug}.json"


def slug_de(nome: str) -> str:
    return slugify(nome, "bloco")


def existe(nome: str) -> bool:
    return _caminho(slug_de(nome)).exists()


def salvar_bloco(nome: str, steps: list[Step], substituir: bool = False) -> Block:
    if not nome.strip():
        raise ValueError("O bloco precisa de um nome.")
    if not steps:
        raise ValueError("Um bloco precisa de pelo menos um passo.")
    if existe(nome) and not substituir:
        # Substituir muda todo teste que usa o bloco; isso tem que ser pedido, nunca
        # acontecer por coincidencia de nome.
        raise ValueError(f'Ja existe um bloco "{nome.strip()}".')

    bloco = Block(
        name=nome.strip(),
        slug=slug_de(nome),
        created_at=datetime.now().isoformat(timespec="seconds"),
        url_inicial=steps[0].url,
        steps=list(steps),
    )
    PASTA.mkdir(parents=True, exist_ok=True)
    _caminho(bloco.slug).write_text(bloco.model_dump_json(indent=2), encoding="utf-8")
    return bloco


def carregar_bloco(slug: str) -> Block | None:
    arquivo = _caminho(slug_de(slug))
    if not arquivo.exists():
        return None
    try:
        return Block.model_validate_json(arquivo.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - arquivo mexido a mao e quebrado
        return None


def listar_blocos() -> list[Block]:
    if not PASTA.exists():
        return []
    blocos = []
    for arquivo in sorted(PASTA.glob("*.json")):
        try:
            blocos.append(Block.model_validate_json(arquivo.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - um arquivo torto nao derruba a lista inteira
            continue
    return blocos


def excluir_bloco(slug: str) -> bool:
    arquivo = _caminho(slug_de(slug))
    if not arquivo.exists():
        return False
    arquivo.unlink()
    return True
