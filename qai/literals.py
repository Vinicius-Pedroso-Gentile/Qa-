"""Extracao deterministica de dados literais do comando.

Este modulo existe por causa de uma falha medida do qwen3:1.7b: quando a LLM e
encarregada de copiar o dado de teste, ela o corrompe -- no experimento inicial
transformou "qualquerCoisa0001@gmail.com" em "anything0001@gmail.com" (traduziu a
palavra). Por isso nenhum valor passa pela LLM: todos sao recortados do texto do
comando por regra.
"""

from __future__ import annotations

import re

from .textutil import normalize, tokens

URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
BARE_DOMAIN_RE = re.compile(r"(?<![@\w.])((?:[\w-]+\.)+[a-z]{2,})(/\S*)?", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
QUOTED_RE = re.compile(r"[\"“”]([^\"“”]{2,})[\"“”]")

# Verbos que anunciam o valor logo em seguida: "digite banana", "preencher com Joao".
MARKER_RE = re.compile(
    r"\b(?:digite|digitar|digito|escreva|escrever|preencha|preencher|"
    r"informe|informar|insira|inserir|coloque|colocar|com|valor|texto)\b",
    re.IGNORECASE,
)

_TRAILING = " .,;:!?\"'“”"

# Artigos e preposicoes que aparecem entre o verbo e o valor.
_FILLER = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "no", "na", "em",
           "campo", "valor", "texto", "seguinte", "barra"}

# Palavras que sao rotulo de campo, nunca valor de teste.
_NOT_A_VALUE = {
    "campo", "senha", "email", "e-mail", "valor", "botao", "botão",
    "aplicacao", "aplicação", "tela", "pagina", "página", "modal", "mensagem",
    "pesquisa", "pesquisar", "busca", "buscar",
    # cortesia que sobra no fim da frase
    "favor", "obrigado", "obrigada", "beleza", "valeu", "please",
}


def find_url(text: str) -> str | None:
    """URL do comando. Aceita tambem dominio digitado sem o https://."""
    match = URL_RE.search(text)
    if match:
        return match.group(0).rstrip(_TRAILING)

    bare = BARE_DOMAIN_RE.search(text)
    if bare and not EMAIL_RE.search(text):
        return "https://" + bare.group(0).rstrip(_TRAILING)
    return None


def find_quoted(text: str) -> list[str]:
    return [m.group(1).strip() for m in QUOTED_RE.finditer(text)]


def _after_colon(text: str) -> str | None:
    if ":" not in text:
        return None
    return text.split(":", 1)[1].strip().strip(_TRAILING) or None


# Simbolos que aparecem dentro de um dado, nunca na pontuacao de uma frase.
_SIMBOLOS_DE_DADO = set(r"@#$%&*_/+\|~^")


def _has_symbol(token: str) -> bool:
    """Digito ou simbolo dentro da palavra -- sinal forte de que aquilo e um dado de
    teste (Teste@123, ABC-99) e nao o nome de um campo.

    Virgula e ponto ficam de fora de proposito: eles sao pontuacao de frase, e
    aceita-los fazia "nome, por favor" passar por valor.
    """
    return any(char.isdigit() or char in _SIMBOLOS_DE_DADO for char in token)


def _echoes_label(token: str, label: str) -> bool:
    """O token e so o nome do campo repetido? ('pesquisa' para o campo 'Pesquisar')."""
    if not label:
        return False
    candidate = normalize(token)
    for word in tokens(label):
        if candidate == word:
            return True
        if len(candidate) >= 4 and (candidate.startswith(word[:4]) or word.startswith(candidate[:4])):
            return True
    return False


# Frases de cortesia que podem sobrar no fim do comando e nao sao valor.
_CORTESIA = {"por favor", "obrigado", "obrigada", "ok", "beleza", "valeu"}


def _acceptable(token: str | None, element_label: str) -> str | None:
    """Filtra candidatos a valor que na verdade sao o nome do campo."""
    if not token:
        return None
    if _has_symbol(token):
        # Teste@123, joao99 -- e tambem "4", o digito da conta: um unico caractere
        # pode ser um valor legitimo, entao o teste de tamanho vem depois deste.
        return token
    if len(token) < 2:
        return None
    if normalize(token) in {normalize(w) for w in _NOT_A_VALUE} or normalize(token) in _CORTESIA:
        return None
    if _echoes_label(token, element_label):
        return None
    return token


def _after_comma(text: str) -> str | None:
    """Valor de varias palavras anunciado apos virgula.

    "coloque no email o seguinte texto, banana pera uva" -> "banana pera uva".
    So vale para 2 a 5 palavras: uma palavra sozinha o _trailing_token ja pega, e
    mais que cinco quase certamente e o resto da frase, nao um valor.
    """
    if "," not in text:
        return None
    cauda = text.rsplit(",", 1)[1].strip().strip(_TRAILING)
    palavras = cauda.split()
    if not (2 <= len(palavras) <= 5):
        return None
    if normalize(cauda) in _CORTESIA:
        return None
    return cauda


def _trailing_token(text: str) -> str | None:
    tokens_ = text.strip().split()
    return tokens_[-1].strip(_TRAILING) if tokens_ else None


def _after_marker(text: str, element_label: str = "") -> str | None:
    """Valor logo depois do verbo.

    "digite banana na barra"        -> "banana"
    "informe o nome Vinicius Gentile" -> "Vinicius Gentile"

    O segundo caso so funciona porque descartamos do inicio os artigos e o proprio
    nome do campo: "o nome" e rotulo, nao valor. Sem isso o valor virava so a ultima
    palavra ("Gentile"), que e errado e silencioso.
    """
    markers = list(MARKER_RE.finditer(text))
    if not markers:
        return None

    words = [w for w in (p.strip(_TRAILING) for p in text[markers[-1].end():].split()) if w]
    while words and not _has_symbol(words[0]) and (
        words[0].lower() in _FILLER or _echoes_label(words[0], element_label)
    ):
        words.pop(0)
    if not words:
        return None
    # Sobrou uma frase inteira? Entao o valor e so a primeira palavra dela.
    return " ".join(words) if len(words) <= 3 else words[0]


def extract_value(text: str, action: str, *, element_label: str = "") -> str | None:
    """Recorta o valor literal de um comando, conforme o tipo de acao."""
    if action == "goto":
        return find_url(text)

    if action == "fill":
        email = EMAIL_RE.search(text)
        if email:
            return email.group(0)
        for quoted in find_quoted(text):
            if not _echoes_label(quoted, element_label):
                return quoted
        return (
            _acceptable(_after_comma(text), element_label)
            or _acceptable(_after_marker(text, element_label), element_label)
            or _acceptable(_trailing_token(text), element_label)
        )

    if action == "expect_text":
        quoted = find_quoted(text)
        if quoted:
            return max(quoted, key=len)  # a mensagem esperada e a maior das aspas
        return _after_colon(text)

    return None


# ---------------------------------------------------------------------------
# Mascaras em texto esperado
# ---------------------------------------------------------------------------
# Mensagens de sistema costumam carregar um dado que muda a cada execucao ("A conta
# 827-9 foi criada com sucesso"). O testador escreve a parte variavel como mascara --
# XXXX-X, ###, * -- e aqui ela vira um curinga de regex. O resto do texto continua
# sendo comparado letra por letra: a validacao nao afrouxa, so ignora o trecho que
# nao tem como ser previsto.

_CURINGA = set("Xx#*.…_-")
_CURINGA_FORTE = set("Xx#*…")


def _e_mascara(palavra: str) -> bool:
    limpa = palavra.strip(".,;:!?()[]")
    if not limpa or not all(c in _CURINGA for c in limpa):
        return False
    # Precisa de pelo menos dois curingas, senao um hifen solto viraria mascara.
    return sum(1 for c in limpa if c in _CURINGA_FORTE) >= 2


def tem_mascara(texto: str) -> bool:
    return any(_e_mascara(palavra) for palavra in (texto or "").split())


def to_pattern(texto: str) -> re.Pattern[str] | None:
    """Converte texto com mascara em regex. Devolve None se nao houver mascara."""
    if not tem_mascara(texto):
        return None

    partes = []
    for palavra in texto.split():
        if _e_mascara(palavra):
            partes.append(r"\S+")
        else:
            partes.append(re.escape(palavra))
    # \s+ entre as palavras: a aplicacao pode quebrar a mensagem em varias linhas.
    return re.compile(r"\s+".join(partes), re.IGNORECASE)
