"""Adapter for the frontend contract in docs/api.md (POST /api/match).

Translation only — no filtering, scoring or ordering happens here:

    FrontendMatchRequest --to_match_request()--> MatchRequest
    matcher.match_with_rejections()               (the one and only engine)
    build_response()  ranked[:3] -> cards, rejection counts -> status/message/excluded

Card explanations are deterministic templates built from real dataset fields
and the matcher's score breakdown (an LLM may rephrase them later, but never
chooses or reorders contractors).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.matcher import (
    REJECT_BUDGET,
    REJECT_BUSY,
    REJECT_CATEGORY,
    REJECT_CITY,
    REJECT_DURATION,
    REJECT_FORMAT,
    REJECT_LANGUAGE,
)
from backend.intent_parser import InterpretedIntent
from backend.models import MatchRequest, ScoredContractor, normalize_text, parse_event_date
from backend.relevance import requested_services

MAX_CARDS = 3

# matcher reason -> docs/api.md `excluded` key. City/category are not here:
# they define the candidate pool (-> status "no_category"), not a "didn't fit".
EXCLUDED_KEYS: dict[str, str] = {
    REJECT_BUSY: "busy_on_date",
    REJECT_BUDGET: "over_budget",
    REJECT_FORMAT: "wrong_format",
    REJECT_LANGUAGE: "wrong_language",
    REJECT_DURATION: "too_few_hours",
}
POOL_RULES = (REJECT_CITY, REJECT_CATEGORY)

_REASON_TEXT = {
    "busy_on_date": "заняты в эту дату",
    "over_budget": "дороже бюджета",
    "wrong_format": "не работают с этим форматом",
    "wrong_language": "не говорят на нужном языке",
    "too_few_hours": "не работают столько часов",
}


# --------------------------------------------------------------------------
# Contract models
# --------------------------------------------------------------------------

class FrontendMatchRequest(BaseModel):
    """Request body exactly as docs/api.md names it. `query` is an optional
    extension (free-text need) that the documented frontend doesn't send."""

    model_config = ConfigDict(frozen=True)

    city: str
    date: str
    event_type: str
    category: str | None = None
    budget_kzt: int | None = Field(default=None, gt=0)
    hours: float | None = Field(default=None, gt=0)
    language: str | None = None
    query: str | None = Field(default=None, max_length=1000)

    @field_validator("date")
    @classmethod
    def _date(cls, v: str) -> str:
        return parse_event_date(v)

    @field_validator("city", "event_type")
    @classmethod
    def _required_text(cls, v: str) -> str:
        if not normalize_text(v):
            raise ValueError("must not be empty")
        return v

    @field_validator("category", "language", "query")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return v if v is not None and normalize_text(v) else None


class Card(BaseModel):
    id: str
    name: str
    category: str
    city: str
    price_from_kzt: int
    synthetic: bool
    explanation: str
    # Extension: True when the query asked for specific services (see
    # FrontendMatchResponse.service_intent) and this contractor offers none of them.
    alternative: bool = False


class ServiceIntent(BaseModel):
    """Extension: services the free-text query asked for (dataset categories)."""

    requested: list[str]    # e.g. ["Видеограф", "Фотограф"]
    unavailable: list[str]  # requested, but no eligible contractor offers it
    not_in_top: list[str]   # eligible contractors offer it, just not in the top 3


class Excluded(BaseModel):
    busy_on_date: int = 0
    over_budget: int = 0
    wrong_format: int = 0
    wrong_language: int = 0
    too_few_hours: int = 0


class FrontendMatchResponse(BaseModel):
    status: Literal["found", "no_category", "none_fit"]
    message: str
    cards: list[Card]
    excluded: Excluded
    # Extension: null when the query names no known service, or when an explicit
    # `category` was sent (that is a hard filter and speaks for itself).
    service_intent: ServiceIntent | None = None
    # Extension: what was understood from `query` (AI parser or deterministic).
    interpreted_intent: InterpretedIntent | None = None


# --------------------------------------------------------------------------
# Translation
# --------------------------------------------------------------------------

def to_match_request(req: FrontendMatchRequest) -> MatchRequest:
    return MatchRequest(
        city=req.city,
        event_format=req.event_type,
        event_date=req.date,
        budget_kzt=req.budget_kzt,
        category=req.category,
        language=req.language,
        duration_hours=req.hours,
        query=req.query,
    )


def _kzt(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₸"


def _count(n: int, one: str, few: str, many: str) -> str:
    """Russian plural: 1 кандидат, 2 кандидата, 5 кандидатов."""
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


def _card_category(s: ScoredContractor, req: MatchRequest) -> str:
    c = s.contractor
    if req.category is not None:
        wanted = normalize_text(req.category)
        for norm, display in zip(c.categories, c.categories_display):
            if norm == wanted:
                return display
    if s.score.matched_categories:
        return ", ".join(s.score.matched_categories)
    return ", ".join(c.categories_display)


def explain(s: ScoredContractor, req: MatchRequest) -> str:
    """Concrete, fact-only reasons this contractor fits (all from the dataset)."""
    c, sc = s.contractor, s.score
    parts = [f"Свободен {date.fromisoformat(req.event_date):%d.%m.%Y}"]

    price = f"цена от {_kzt(c.price_from_kzt)}"
    if req.budget_kzt is not None:
        price += f" при бюджете {_kzt(req.budget_kzt)}"
    if c.price_imputed:
        price += " (цена оценочная)"
    parts.append(price)

    parts.append(f"работает на мероприятиях формата «{req.event_format}»")
    if sc.matched_categories and req.category is None:
        parts.append(f"категория «{', '.join(sc.matched_categories)}» соответствует запросу")
    if sc.matched_terms:
        parts.append(f"в описании упоминается: {', '.join(sc.matched_terms)}")
    if req.language is not None:
        parts.append(f"говорит на языке: {normalize_text(req.language)}")
    if req.duration_hours is not None:
        if c.max_hours is not None:
            parts.append(f"работает до {c.max_hours:g} ч (нужно {req.duration_hours:g} ч)")
        else:
            parts.append("максимальная длительность не указана — стоит уточнить")
    if c.synthetic:
        parts.append("профиль синтетический (демо-данные)")
    return "; ".join(parts) + "."


def with_explanations(
    response: FrontendMatchResponse, texts: dict[str, str]
) -> FrontendMatchResponse:
    """Swap in explanation texts looked up by card id.

    Iterates response.cards (the matcher's order) — never `texts` — so the
    cards, their order and every other field stay exactly as they were. Ids in
    `texts` that aren't on a card are ignored.
    """
    alt_prefix = _alternative_prefix(response.service_intent)
    cards = []
    for card in response.cards:
        if card.id in texts:
            text = texts[card.id]
            # Python, not the LLM, decides what is an alternative — keep it visible.
            if card.alternative and "альтернатив" not in text.lower():
                text = alt_prefix + text
            card = card.model_copy(update={"explanation": text})
        cards.append(card)
    return response.model_copy(update={"cards": cards})


def with_interpreted_intent(
    response: FrontendMatchResponse, intent: InterpretedIntent | None
) -> FrontendMatchResponse:
    """Attach what the query was understood as; say so if it narrowed the search."""
    message = response.message
    if intent is not None and "language" in intent.applied:
        message += f" Из текста запроса учтено: язык — {intent.language}."
    return response.model_copy(update={"interpreted_intent": intent, "message": message})


def _reasons(excluded: Excluded) -> str:
    items = [(k, v) for k, v in excluded.model_dump().items() if v]
    return ", ".join(f"{_REASON_TEXT[k]} — {v}" for k, v in items)


def _quoted(names: list[str]) -> str:
    return ", ".join(f"«{n}»" for n in names)


def _alternative_prefix(intent: ServiceIntent | None) -> str:
    return f"Альтернатива (не {_quoted(intent.requested)}): " if intent else ""


def _service_intent(
    ranked: list[ScoredContractor],
    req: MatchRequest,
    known_categories: Mapping[str, str] | None,
) -> tuple[ServiceIntent | None, set[str]]:
    """(intent, ids of shown cards that offer a requested service).

    Reads the matcher's own matched_categories — decides nothing about ranking.
    """
    if req.category is not None or not known_categories:
        return None, set()
    wanted = requested_services(req, known_categories)
    if not wanted:
        return None, set()

    def offers(s: ScoredContractor) -> set[str]:
        return {normalize_text(m) for m in s.score.matched_categories} & set(wanted)

    available = {n for s in ranked for n in offers(s)}
    top = ranked[:MAX_CARDS]
    shown = {n for s in top for n in offers(s)}
    intent = ServiceIntent(
        requested=[known_categories[n] for n in wanted],
        unavailable=[known_categories[n] for n in wanted if n not in available],
        not_in_top=[known_categories[n] for n in wanted if n in available and n not in shown],
    )
    return intent, {s.contractor.id for s in top if offers(s)}


def build_response(
    ranked: list[ScoredContractor],
    rejected: dict[str, int],
    req: MatchRequest,
    known_categories: Mapping[str, str] | None = None,
) -> FrontendMatchResponse:
    """Shape the matcher's output. `ranked` order is kept exactly; only cut to 3.

    known_categories (normalized -> display) enables service-intent messages:
    if the query asks for e.g. «Ведущий» and no eligible contractor is one, the
    cards are still the matcher's top 3, but flagged `alternative` and the
    message says so.
    """
    excluded = Excluded(**{
        key: rejected.get(reason, 0) for reason, key in EXCLUDED_KEYS.items()
    })
    pool = len(ranked) + sum(v for k, v in rejected.items() if k not in POOL_RULES)
    intent, offering = _service_intent(ranked, req, known_categories)
    alt_prefix = _alternative_prefix(intent)

    cards = []
    for s in ranked[:MAX_CARDS]:
        alternative = intent is not None and s.contractor.id not in offering
        cards.append(Card(
            id=s.contractor.id,
            name=s.contractor.anon_name,
            category=_card_category(s, req),
            city=s.contractor.city,
            price_from_kzt=s.contractor.price_from_kzt,
            synthetic=s.contractor.synthetic,
            explanation=(alt_prefix if alternative else "") + explain(s, req),
            alternative=alternative,
        ))

    if pool == 0:
        message = (f"В городе {req.city} нет подрядчиков категории «{req.category}»."
                   if req.category else f"В городе {req.city} нет подрядчиков.")
        return FrontendMatchResponse(status="no_category", message=message, cards=[],
                                     excluded=excluded, service_intent=intent)

    candidates = _count(pool, "кандидат", "кандидата", "кандидатов")
    if not ranked:
        return FrontendMatchResponse(
            status="none_fit",
            message=f"Никто из {candidates} не подошёл: {_reasons(excluded)}.",
            cards=[], excluded=excluded, service_intent=intent)

    if len(ranked) > MAX_CARDS:
        message = f"Подходят {len(ranked)} из {candidates}; показаны {MAX_CARDS} лучших."
    elif len(ranked) == MAX_CARDS:
        message = f"Подходят {MAX_CARDS} из {candidates}."
    elif sum(excluded.model_dump().values()):
        message = f"Подходят только {len(ranked)} из {candidates}: остальные {_reasons(excluded)}."
    else:
        message = f"Всего {candidates} под этот запрос, все подходят."

    if intent is not None:
        if intent.unavailable == intent.requested:
            message += (f" По вашим условиям не нашлось: {_quoted(intent.unavailable)} — "
                        f"показаны другие доступные подрядчики (альтернативы).")
        elif intent.unavailable:
            message += f" Не нашлось: {_quoted(intent.unavailable)}."
        if intent.not_in_top:
            message += (f" Есть и {_quoted(intent.not_in_top)}, но не в первой тройке — "
                        f"уточните запрос.")
    return FrontendMatchResponse(status="found", message=message, cards=cards,
                                 excluded=excluded, service_intent=intent)
