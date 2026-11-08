"""Deterministic parsing of resident replies (no network, no AI).

Everything here is pure: it normalizes text, recognizes global commands
(OPW-018), yes/no, "no sé", numbers and option choices, and redacts text before
the optional OpenAI extraction ever sees it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Global commands, recognized at any step as the whole message (OPW-017/018).
COMMANDS = {
    "ayuda": "help",
    "humano": "help",
    "persona": "help",
    "baja": "optout",
    "stop": "optout",
    "corregir": "correct",
    "actualizar": "update",
    "donde": "where",
    "permisos": "permissions",
    "borrar": "delete",
    "menu": "menu",
    "atras": "back",
    "volver": "back",
}

_YES = {"si", "s", "sí", "claro", "ok", "dale", "correcto", "acepto", "yes", "afirmativo",
        "confirmar", "confirmo", "de acuerdo"}
_NO = {"no", "n", "nop", "nunca", "negativo", "no acepto", "no gracias"}
_DONT_KNOW = {"no se", "nose", "ns", "no lo se", "no sabria", "ni idea", "desconozco"}

_NUMBER_WORDS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "cien": 100,
}


def normalize(text: str | None) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def command_of(text: str | None) -> str | None:
    return COMMANDS.get(normalize(text))


def is_dont_know(text: str | None) -> bool:
    return normalize(text) in _DONT_KNOW


def yes_no(text: str | None) -> bool | None:
    t = normalize(text)
    if t in _YES or t.startswith("si "):
        return True
    if t in _NO or t.startswith("no ") and t not in _DONT_KNOW:
        return False
    return None


def parse_int(text: str | None, lo: int = 0, hi: int = 10_000) -> int | None:
    """A single number in the reply: digits ("5", "5 personas") or a word ("cinco")."""
    t = normalize(text)
    if not t:
        return None
    nums = re.findall(r"\d+", t)
    if len(nums) == 1:
        n = int(nums[0])
        return n if lo <= n <= hi else None
    if not nums:
        words = [w for w in t.split() if w in _NUMBER_WORDS]
        if len(words) == 1:
            n = _NUMBER_WORDS[words[0]]
            return n if lo <= n <= hi else None
    return None


@dataclass(frozen=True)
class Option:
    id: str
    title: str
    description: str | None = None
    synonyms: tuple[str, ...] = field(default_factory=tuple)


def match_option(options: list[Option], *, choice_id: str | None, text: str | None
                 ) -> Option | None:
    """Pick an option by button/list id, by its number (1-based), or by text."""
    if choice_id:
        for o in options:
            if o.id == choice_id:
                return o
    t = normalize(text)
    if not t:
        return None
    if t.isdigit():
        i = int(t)
        return options[i - 1] if 1 <= i <= len(options) else None
    for o in options:
        if t == normalize(o.title) or t in (normalize(s) for s in o.synonyms):
            return o
    return None


# ---------------------------------------------------------------------------
# Area matching (OPW-013): exact name/alias, then token overlap.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AreaCandidate:
    id: str
    name: str
    aliases: tuple[str, ...] = ()


def match_areas(candidates: list[AreaCandidate], text: str | None, limit: int = 3
                ) -> list[AreaCandidate]:
    """Return [one] for an unambiguous match, up to ``limit`` for ambiguous input,
    [] when nothing matches."""
    t = normalize(text)
    if not t:
        return []
    exact = [c for c in candidates
             if t == normalize(c.name) or t in (normalize(a) for a in c.aliases)]
    if exact:
        return exact[:limit]
    contains = [c for c in candidates
                if normalize(c.name) in t or any(normalize(a) in t for a in c.aliases if a)]
    if len(contains) == 1:
        return contains
    tokens = set(t.split()) - {"de", "la", "el", "los", "las", "en", "sector", "parroquia"}
    scored = []
    for c in candidates:
        names = [normalize(c.name), *(normalize(a) for a in c.aliases)]
        best = max(len(tokens & (set(n.split()) - {"sector", "parroquia", "de"})) for n in names)
        if best:
            scored.append((best, c))
    scored.sort(key=lambda x: -x[0])
    if contains:
        return contains[:limit]
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return [scored[0][1]]
    return [c for _, c in scored[:limit]]


# ---------------------------------------------------------------------------
# Redaction before the optional OpenAI call (amended OPW-023).
# ---------------------------------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
_URL = re.compile(r"https?://\S+|www\.\S+")
_ID_LIKE = re.compile(r"\b[VvEeJj]-?\d{6,9}\b")  # Venezuelan cédula / RIF


def redact(text: str, max_chars: int = 280) -> str:
    """Remove contact details and identifiers; cap length."""
    t = _URL.sub("[enlace]", text)
    t = _EMAIL.sub("[correo]", t)
    t = _ID_LIKE.sub("[documento]", t)
    t = _PHONE.sub("[número]", t)
    return t.strip()[:max_chars]
