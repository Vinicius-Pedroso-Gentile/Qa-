"""Interpretacao de um comando em linguagem natural pela LLM.

Sao duas perguntas, cada uma pequena e com resposta restrita a uma lista fechada:

  1. Que acao e esta?            -> goto | fill | click | expect_text | locate
  2. Qual elemento ela usa?      -> um dos ids do inventario real da pagina

O formato foi escolhido por medicao. Pedir a interpretacao inteira de uma vez ao
qwen3:1.7b produz resposta degenerada; uma decisao por vez, com enum e few-shot,
acerta de forma consistente.
"""

from __future__ import annotations

import re

from .literals import find_quoted
from .llm import classify, enum_schema
from .models import CHAT_ACTIONS, Action, PageElement
from .textutil import tokens

NO_ELEMENT = "NENHUM"

ACTION_SYSTEM = (
    "Classifique a acao de UM comando de teste web.\n"
    "goto = abrir uma URL, acessar um site\n"
    "fill = digitar, informar ou preencher um valor em um campo\n"
    "click = clicar ou pressionar um botao ou link\n"
    "expect_text = validar, verificar ou conferir que algo e apresentado na tela;\n"
    "  so vale quando o comando diz qual texto deve aparecer\n"
    "locate = apenas localizar ou identificar um campo, sem interagir com ele\n"
    "Responda apenas com o JSON."
)

ACTION_EXAMPLES = [
    ("COMANDO: Abrir o site https://exemplo.com", '{"action": "goto"}'),
    ("COMANDO: Localizar o campo Telefone.", '{"action": "locate"}'),
    ("COMANDO: Preencher o campo Nome com Joao", '{"action": "fill"}'),
    ("COMANDO: Pressionar o botao Enviar", '{"action": "click"}'),
    ("COMANDO: Verificar que a tela exibe Cadastro concluido", '{"action": "expect_text"}'),
    # "confirmacao" puxa o modelo para expect_text; este exemplo desfaz isso.
    ("COMANDO: Informe a confirmacao da senha Teste@123", '{"action": "fill"}'),
    ("COMANDO: Apague o que esta no campo Nome", '{"action": "clear"}'),
    ("COMANDO: limpe o campo", '{"action": "clear"}'),
]


async def choose_action(text: str) -> Action:
    result = await classify(
        system=ACTION_SYSTEM,
        examples=ACTION_EXAMPLES,
        user=f"COMANDO: {text}",
        schema=enum_schema(action=[a.value for a in CHAT_ACTIONS]),
        run_name="escolher_acao",
    )
    try:
        return Action(result.get("action", ""))
    except ValueError:
        return Action.LOCATE


_VERBOS_DE_VALIDACAO = re.compile(
    r"\b(?:valid\w*|verifi(?:c|qu)\w*|confir\w*|confer\w*|che(?:c|qu)\w*)\b",
    re.IGNORECASE,
)


def parece_validacao(text: str) -> bool:
    """A LLM disse que e validacao -- mas e mesmo?

    expect_text so faz sentido quando o comando diz qual texto deve aparecer. Sem
    texto esperado e sem nenhum verbo de validacao, o que o modelo viu foi o nome do
    campo, nao uma ordem de conferir: "informe a descricao Pagamento teste" e
    "informe a confirmacao da senha" sao preenchimentos, e o modelo tropeca nos dois.
    """
    if find_quoted(text) or ":" in text:
        return True
    return bool(_VERBOS_DE_VALIDACAO.search(text))


def _fuzzy(text: str, elements: list[PageElement]) -> PageElement | None:
    """Rede de seguranca deterministica, caso a LLM nao devolva um id valido."""
    wanted = tokens(text)
    best, best_score = None, 0
    for element in elements:
        score = len(wanted & tokens(f"{element.name} {element.input_type}"))
        if score > best_score:
            best, best_score = element, score
    return best


async def choose_element(text: str, elements: list[PageElement]) -> PageElement | None:
    if not elements:
        return None

    catalog = "\n".join(f"{e.element_id} = {e.describe()}" for e in elements)
    system = (
        "Escolha qual elemento da pagina o comando utiliza.\n\n"
        f"ELEMENTOS DISPONIVEIS:\n{catalog}\n\n"
        f"Responda apenas com o JSON, usando um dos ids acima ou {NO_ELEMENT}."
    )
    valid = [e.element_id for e in elements]

    result = await classify(
        system=system,
        examples=[],
        user=f"COMANDO: {text}",
        schema=enum_schema(element=valid + [NO_ELEMENT]),
        run_name="escolher_elemento",
    )

    chosen = result.get("element")
    by_id = {e.element_id: e for e in elements}
    if chosen in by_id and _plausible(text, by_id[chosen]):
        return by_id[chosen]
    return _fuzzy(text, elements)


def _plausible(text: str, element: PageElement) -> bool:
    """Confere a escolha da LLM contra o texto do comando.

    O enum obriga o modelo a devolver algum id valido, entao ele sempre escolhe
    alguma coisa -- pedimos "clicar no botao Transferencia" numa pagina que nao tem
    esse botao e ele respondeu "Cadastrar". Exigir ao menos uma palavra em comum
    entre o comando e o nome do elemento transforma esse palpite em "nao encontrei",
    que e a resposta honesta.
    """
    return bool(tokens(text) & tokens(element.name))


def disambiguate(
    chosen: PageElement | None,
    elements: list[PageElement],
    active_form: str,
) -> PageElement | None:
    """Desempata quando o mesmo campo existe em mais de um formulario da pagina.

    No BugBank, os formularios de login e de cadastro coexistem no DOM e ambos tem um
    campo "Informe seu e-mail". Olhando so para o comando isolado, a escolha e ambigua
    ate para uma pessoa. Duas regras resolvem:

    1. Se o usuario ja interagiu com algum formulario, e nele que ele esta trabalhando.
    2. Sem esse contexto, vale o primeiro formulario da pagina.
    """
    if chosen is None or not chosen.form:
        return chosen

    twins = [e for e in elements if e.name == chosen.name and e.role == chosen.role]
    if len(twins) < 2:
        return chosen

    if active_form:
        for twin in twins:
            if twin.form == active_form:
                return twin
    return twins[0]


def only_text_field(elements: list[PageElement]) -> PageElement | None:
    """O unico campo de texto da pagina, se so houver um.

    Serve para comandos que nao nomeiam o campo -- "Digite banana" no Google. Nao ha
    o que desambiguar quando so existe um lugar onde digitar.
    """
    campos = [e for e in elements if e.editable]
    return campos[0] if len(campos) == 1 else None
