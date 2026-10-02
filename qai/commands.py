"""Quebra uma mensagem com varias ordens em comandos separados.

"Coloque no campo senha Vinicius, e logo em seguida clique em acessar"
    -> ["Coloque no campo senha Vinicius", "clique em acessar"]

A divisao e deterministica, feita antes de qualquer LLM. E de proposito: pedir ao
qwen3:1.7b que processe varias acoes de uma vez e exatamente o cenario em que ele
degenera. Separando aqui, cada pedaco volta a ser a pergunta pequena que ele acerta.

Para nao cortar no lugar errado, duas travas:
  * texto entre aspas e protegido -- uma mensagem de validacao pode conter virgulas
    e a palavra "verifique" dentro dela;
  * so corta quando o pedaco seguinte comeca com um verbo de acao, entao "Joao e
    Maria" continua sendo um valor so.
"""

from __future__ import annotations

import re

# Verbos que iniciam uma ordem nova.
# Atencao ao radical: em portugues varios desses verbos alternam c/qu entre as
# formas (clicar / clique, verificar / verifique), entao o padrao precisa aceitar os
# dois -- "clic\w*" sozinho nao casa com "clique".
_VERBS = (
    r"(?:cli(?:c|qu)\w*|verifi(?:c|qu)\w*|mar(?:c|qu)\w*|colo(?:c|qu)\w*|"
    r"aperte|apertar|pression\w*|preench\w*|digit\w*|escrev\w*|"
    r"inform\w*|insir\w*|inser\w*|valid\w*|confir\w*|acess\w*|abr\w*|"
    r"localiz\w*|encontr\w*|selecion\w*|navegue|navegar|v[aá]\s)"
)

# Conector obrigatorio + verbo a seguir.
_SPLIT_RE = re.compile(
    r"(?:[,;]\s*(?:e\s+)?|\s+e\s+)"
    r"(?:logo\s+)?(?:em\s+seguida\s*,?\s*|depois\s*,?\s*|ent[aã]o\s*,?\s*)?"
    r"(?=" + _VERBS + r")",
    re.IGNORECASE,
)

_QUOTED_RE = re.compile(r"[\"“”][^\"“”]*[\"“”]")
_PLACEHOLDER = "\x00{}\x00"


def _mask(text: str) -> tuple[str, list[str]]:
    guardados: list[str] = []

    def troca(match: re.Match) -> str:
        guardados.append(match.group(0))
        return _PLACEHOLDER.format(len(guardados) - 1)

    return _QUOTED_RE.sub(troca, text), guardados


def _unmask(text: str, guardados: list[str]) -> str:
    for indice, original in enumerate(guardados):
        text = text.replace(_PLACEHOLDER.format(indice), original)
    return text


def split_commands(text: str) -> list[str]:
    """Uma mensagem pode conter varias ordens. Devolve uma lista com pelo menos uma."""
    mascarado, guardados = _mask(text)
    pedacos = [
        _unmask(pedaco, guardados).strip(" ,;.")
        for pedaco in _SPLIT_RE.split(mascarado)
    ]
    limpos = [pedaco for pedaco in pedacos if pedaco]
    return limpos or [text.strip()]
