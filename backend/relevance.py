"""Deterministic text relevance between a request and a contractor.

No LLMs, embeddings, randomness or external services — only transparent
token overlap, so every score can be explained term by term.

Pipeline
--------
1. tokenize()   lowercase, ё->е, drop punctuation (Unicode-aware, so Kazakh
                letters ә ғ қ ң ө ұ ү һ і survive), drop stop words.
2. stem()       strip ONE common Russian ending (keeps >= 4 letters), so
                "фотографа" / "фотографы" -> "фотограф".
3. analyze_request()  turns query (+ explicit category) into "need" terms.
                Words that only repeat hard-filtered fields (the event format,
                the city) are removed — every survivor already satisfies them.
4. relevance()  per contractor:

      category_match       1.0 if any of the contractor's categories matches
                           the need (whole category name, a keyword from
                           CATEGORY_KEYWORDS, or the explicit category),
                           else 0.0
      description_overlap  share of need terms found in the description

      relevance = 0.8 * category_match + 0.2 * description_overlap   (0..1)

   A whole category match is worth 4x full description overlap, so a
   contractor merely *mentioning* a word can't beat one that *is* that service.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from backend.models import Contractor, MatchRequest, normalize_text

W_CATEGORY_MATCH = 0.8
W_DESCRIPTION = 0.2

MIN_STEM = 4          # never stem a word below this many letters
MIN_PREFIX_MATCH = 5  # two stems match by prefix only if the shorter is >= this

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)

STOP_WORDS = frozenset({
    # Russian
    "и", "в", "во", "на", "для", "с", "со", "по", "к", "ко", "от", "до", "из", "у",
    "о", "об", "а", "но", "или", "не", "же", "ли", "бы", "мы", "я", "вы", "нам",
    "мне", "нас", "наш", "наша", "наше", "наши", "это", "этот", "эта", "есть",
    "нужен", "нужна", "нужно", "нужны", "ищем", "ищу", "хотим", "хочу", "надо",
    "чтобы", "который", "которая", "которые", "также", "еще", "очень", "пожалуйста",
    "человек", "мероприятие", "мероприятия", "event",
    # Kazakh
    "және", "үшін", "керек", "бар", "мен", "да", "де",
    # English
    "the", "a", "an", "and", "or", "for", "of", "to", "in", "on", "with", "need",
    "we", "i", "please",
})

# One ending stripped per word, longest first.
_SUFFIXES = tuple(sorted({
    "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими", "ией", "иях",
    "ах", "ях", "ом", "ем", "ой", "ей", "ую", "юю", "ая", "яя", "ое", "ее", "ые",
    "ие", "ый", "ий", "ов", "ев", "ам", "ям",
    "а", "я", "ы", "и", "у", "ю", "о", "е", "ь", "й",
}, key=lambda s: (-len(s), s)))

# Extra words that signal a dataset category. A keyword ending in "*" is a
# prefix of a query word ("танц*" -> "танцы", "танцоров"); otherwise it must
# equal the word or its stem. The category's own name always counts too.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "фотограф": ("фото", "фотограф*", "фотосъем*", "фотосесс*", "photo*"),
    "видеограф": ("видео", "видеограф*", "видеосъем*", "клип*", "video*"),
    "ведущий": ("ведущ*", "тамад*", "конферансье", "host*"),
    "ведущий церемонии": ("церемон*", "регистрац*"),
    "банкетный зал": ("банкет*", "зал", "зала", "зале", "залы"),
    "ресторан": ("ресторан*", "кафе"),
    "лайв-бэнд": ("лайв*", "бэнд*", "band*", "кавер*", "группа", "группу"),
    "шоу-программа": ("шоу", "show*", "артист*"),
    "национальный ансамбль": ("ансамбл*", "национальн*", "домбр*", "этно*"),
    "танцевальный коллектив": ("танц*", "dance*"),
    "загородная площадка": ("загородн*", "площадк*", "усадьб*"),
    "флорист": ("флорист*", "цвет*", "букет*", "flower*"),
    "декоратор": ("декор*", "оформлен*"),
    "подарки и сувениры": ("подар*", "сувенир*"),
    "инструменталист": ("инструментал*", "скрип*", "саксофон*", "пианист*", "музыкант*"),
    "фото и видеобудки": ("будк*", "фотобудк*", "видеобудк*"),
    "отель": ("отел*", "гостиниц*", "hotel*", "проживан*"),
}


# --------------------------------------------------------------------------
# Text primitives
# --------------------------------------------------------------------------

def tokenize(text: str | None) -> tuple[str, ...]:
    """Normalized words, stop words removed, order kept, duplicates dropped."""
    cleaned = _NON_WORD.sub(" ", normalize_text(text).replace("ё", "е")).replace("_", " ")
    out: list[str] = []
    for tok in cleaned.split():
        if tok not in STOP_WORDS and not tok.isdigit() and tok not in out:
            out.append(tok)
    return tuple(out)


def stem(token: str) -> str:
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= MIN_STEM:
            return token[: -len(suffix)]
    return token


def stems_match(a: str, b: str) -> bool:
    if a == b:
        return True
    shorter = min(len(a), len(b))
    return shorter >= MIN_PREFIX_MATCH and (a.startswith(b) or b.startswith(a))


def _keyword_hits(keyword: str, tokens: tuple[str, ...]) -> bool:
    if keyword.endswith("*"):
        prefix = keyword[:-1]
        return any(t.startswith(prefix) for t in tokens)
    return any(t == keyword or stem(t) == keyword for t in tokens)


@lru_cache(maxsize=4096)
def text_stems(text: str) -> frozenset[str]:
    return frozenset(stem(t) for t in tokenize(text))


# --------------------------------------------------------------------------
# Request analysis (done once per request)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RequestIntent:
    tokens: tuple[str, ...]          # need words (normalized, unstemmed)
    stems: tuple[str, ...]           # same, stemmed, deduplicated, order kept
    explicit_category: str | None    # normalized req.category
    services: frozenset[str] = frozenset()  # normalized req.services

    @property
    def has_intent(self) -> bool:
        return bool(self.stems) or self.explicit_category is not None or bool(self.services)


def analyze_request(req: MatchRequest) -> RequestIntent:
    filtered_out = text_stems(f"{req.event_format} {req.city}")
    tokens: list[str] = []
    stems: list[str] = []
    for tok in tokenize(f"{req.query or ''} {req.category or ''}"):
        s = stem(tok)
        if any(stems_match(s, f) for f in filtered_out):
            continue  # e.g. "свадьбу" when event_format is "свадьба"
        tokens.append(tok)
        if s not in stems:
            stems.append(s)
    return RequestIntent(
        tokens=tuple(tokens),
        stems=tuple(stems),
        explicit_category=normalize_text(req.category) if req.category else None,
        services=frozenset(normalize_text(s) for s in req.services or ()),
    )


def category_matches(category: str, intent: RequestIntent) -> bool:
    """Does this (normalized) contractor category satisfy the request's need?"""
    if intent.explicit_category == category or category in intent.services:
        return True
    if not intent.tokens:
        return False
    # Whole category name: every word of it appears in the need.
    name_stems = [stem(t) for t in tokenize(category)]
    if name_stems and all(any(stems_match(n, q) for q in intent.stems) for n in name_stems):
        return True
    return any(_keyword_hits(k, intent.tokens) for k in CATEGORY_KEYWORDS.get(category, ()))


def requested_services(req: MatchRequest, known_categories: Iterable[str]) -> tuple[str, ...]:
    """Known (normalized) categories the free-text query asks for, sorted.

    Uses exactly the same matching as contractor relevance, so "service asked
    for" and "contractor provides it" can never disagree. req.category is
    ignored here — an explicit category is a hard filter, not an intent.
    """
    intent = analyze_request(req.model_copy(update={"category": None}))
    return tuple(sorted(c for c in set(known_categories) if category_matches(c, intent)))


# --------------------------------------------------------------------------
# Per-contractor relevance
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Relevance:
    score: float                             # 0..1
    category_match: float                    # 0 or 1
    description_overlap: float               # 0..1
    matched_categories: tuple[str, ...]      # display spelling
    matched_terms: tuple[str, ...]           # need stems found in description


def relevance(c: Contractor, intent: RequestIntent) -> Relevance:
    matched = tuple(
        display
        for norm, display in zip(c.categories, c.categories_display)
        if category_matches(norm, intent)
    )
    category_match = 1.0 if matched else 0.0

    desc = text_stems(c.description)
    terms = tuple(q for q in intent.stems if any(stems_match(q, d) for d in desc))
    overlap = len(terms) / len(intent.stems) if intent.stems else 0.0

    return Relevance(
        score=W_CATEGORY_MATCH * category_match + W_DESCRIPTION * overlap,
        category_match=category_match,
        description_overlap=overlap,
        matched_categories=matched,
        matched_terms=terms,
    )
