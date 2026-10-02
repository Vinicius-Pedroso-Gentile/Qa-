"""Normalizacao de texto em portugues (acentos atrapalham qualquer comparacao)."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()


def slugify(text: str, padrao: str) -> str:
    """'Login inválido' -> 'login-invalido'. Vira nome de arquivo."""
    limpo = re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-")
    return limpo or padrao


def tokens(text: str) -> set[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in normalize(text))
    return {token for token in cleaned.split() if len(token) > 2}
