"""Deterministic contractor matching: hard filters first, then ranking.

Pipeline:
    all contractors
        -> hard_filter()   removes anyone who CANNOT do the event (incl. busy dates)
        -> score()         ranks the survivors: text relevance to the stated need
                           (backend/relevance.py) + real dataset fields
        -> sort by (-score, id)

Only contractors that pass every hard filter are ever scored or returned, so a
contractor who is busy on the requested date can never reach ranking (or any
later LLM stage built on top of match()).

No randomness, no clock, no hash-order dependence: the same request against the
same dataset always yields the same ordering.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.models import (
    Contractor,
    MatchRequest,
    ScoreBreakdown,
    ScoredContractor,
    normalize_text,
)
from backend.relevance import RequestIntent, analyze_request, relevance

# --------------------------------------------------------------------------
# Hard filters
# --------------------------------------------------------------------------

REJECT_CITY = "city"
REJECT_FORMAT = "event_format"
REJECT_BUSY = "busy_date"
REJECT_BUDGET = "budget"
REJECT_CATEGORY = "category"
REJECT_LANGUAGE = "language"
REJECT_DURATION = "duration"


def rejection_reason(c: Contractor, req: MatchRequest) -> str | None:
    """Return the first hard rule the contractor violates, or None if eligible.

    Order matters only for which reason gets counted, never for eligibility.
    City and category come first: they define the candidate pool ("who could
    this request be about at all"); the later rules explain why a candidate
    from that pool doesn't fit this particular date/budget/format/etc.
    """
    if c.city_norm != normalize_text(req.city):
        return REJECT_CITY
    if req.category is not None and normalize_text(req.category) not in c.categories:
        return REJECT_CATEGORY
    if normalize_text(req.event_format) not in c.event_formats:
        return REJECT_FORMAT
    # busy_dates = dates the contractor is NOT available.
    # req.event_date is already canonical ISO (validated in MatchRequest).
    if req.event_date in c.busy_dates:
        return REJECT_BUSY
    if req.budget_kzt is not None and c.price_from_kzt > req.budget_kzt:
        return REJECT_BUDGET
    if req.language is not None and normalize_text(req.language) not in c.languages:
        return REJECT_LANGUAGE
    # Missing max_hours means "unknown", not "zero" -> we don't reject on it.
    if (
        req.duration_hours is not None
        and c.max_hours is not None
        and req.duration_hours > c.max_hours
    ):
        return REJECT_DURATION
    return None


def hard_filter(
    contractors: Iterable[Contractor], req: MatchRequest
) -> tuple[list[Contractor], dict[str, int]]:
    """Split contractors into eligible ones and a count of rejections per rule."""
    eligible: list[Contractor] = []
    rejected: dict[str, int] = {}
    for c in contractors:
        reason = rejection_reason(c, req)
        if reason is None:
            eligible.append(c)
        else:
            rejected[reason] = rejected.get(reason, 0) + 1
    return eligible, rejected


# --------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------
#
# Every component is in 0..1. Two weight sets:
#
# mode "relevance" — the request states a need (query and/or category):
#     total = 0.50 * relevance        (see backend/relevance.py)
#           + 0.25 * budget
#           + 0.15 * confidence
#           + 0.10 * specialization
#
# mode "structured" — no query, no category (nothing to be relevant TO):
#     total = 0.70 * budget
#           + 0.30 * confidence
#
# budget          max(0, 1 - price / budget) if a budget is given, else 0.
#                 Cheaper relative to the budget -> higher; exactly at the
#                 budget -> 0 (still eligible, just no bonus).
# confidence      Preference for data the organizers did NOT fabricate:
#                   0.4 if synthetic is False
#                 + 0.3 if price_imputed is False
#                 + 0.3 if city_imputed is False
# specialization  matched categories / all categories of the contractor,
#                 0 if none match. A pure photographer asked for photos
#                 scores 1.0; a 3-in-1 contractor matching once scores 0.33.
#
# Language and category are HARD FILTERS only; they add nothing to the score
# (every survivor would get the same value, which says nothing).
#
# Guarantee (relevance mode): a contractor whose category matches the need
# always outranks one with no category match and no description overlap,
# whatever their prices or data flags:
#     worst matched   >= 0.50 * 0.8 + 0.10 * (1/3)  = 0.433  (3-category max in data)
#     best unrelated  <= 0.25 * 1   + 0.15 * 1      = 0.400
#
# Scores are rounded to 6 decimals before sorting so float noise can never
# flip an order; ties are broken by contractor id ascending.

MODE_RELEVANCE = "relevance"
MODE_STRUCTURED = "structured"

WEIGHTS: dict[str, dict[str, float]] = {
    MODE_RELEVANCE: {
        "relevance": 0.50, "budget": 0.25, "confidence": 0.15, "specialization": 0.10,
    },
    MODE_STRUCTURED: {
        "relevance": 0.0, "budget": 0.70, "confidence": 0.30, "specialization": 0.0,
    },
}

CONF_REAL_RECORD = 0.4
CONF_REAL_PRICE = 0.3
CONF_REAL_CITY = 0.3

SCORE_DECIMALS = 6


def _round(x: float) -> float:
    return round(x, SCORE_DECIMALS)


def budget_score(c: Contractor, req: MatchRequest) -> float:
    if req.budget_kzt is None:
        return 0.0
    return max(0.0, 1.0 - c.price_from_kzt / req.budget_kzt)


def confidence_score(c: Contractor) -> float:
    return (
        (CONF_REAL_RECORD if not c.synthetic else 0.0)
        + (CONF_REAL_PRICE if not c.price_imputed else 0.0)
        + (CONF_REAL_CITY if not c.city_imputed else 0.0)
    )


def score(
    c: Contractor, req: MatchRequest, intent: RequestIntent | None = None
) -> ScoreBreakdown:
    intent = intent if intent is not None else analyze_request(req)
    mode = MODE_RELEVANCE if intent.has_intent else MODE_STRUCTURED
    w = WEIGHTS[mode]

    rel = relevance(c, intent)
    budget = budget_score(c, req)
    confidence = confidence_score(c)
    specialization = (
        len(rel.matched_categories) / len(c.categories)
        if rel.matched_categories and c.categories
        else 0.0
    )

    total = (
        w["relevance"] * rel.score
        + w["budget"] * budget
        + w["confidence"] * confidence
        + w["specialization"] * specialization
    )
    return ScoreBreakdown(
        mode=mode,
        relevance=_round(rel.score),
        category_match=_round(rel.category_match),
        description_overlap=_round(rel.description_overlap),
        budget=_round(budget),
        confidence=_round(confidence),
        specialization=_round(specialization),
        total=_round(total),
        matched_categories=rel.matched_categories,
        matched_terms=rel.matched_terms,
    )


def rank(eligible: Iterable[Contractor], req: MatchRequest) -> list[ScoredContractor]:
    intent = analyze_request(req)  # once per request, not per contractor
    scored = [ScoredContractor(contractor=c, score=score(c, req, intent)) for c in eligible]
    scored.sort(key=lambda s: (-s.score.total, s.contractor.id))
    return scored


def match(contractors: Iterable[Contractor], req: MatchRequest) -> list[ScoredContractor]:
    """Full deterministic pipeline: hard filter, then rank."""
    eligible, _ = hard_filter(contractors, req)
    return rank(eligible, req)


def match_with_rejections(
    contractors: Iterable[Contractor], req: MatchRequest
) -> tuple[list[ScoredContractor], dict[str, int]]:
    """Same as match(), plus how many contractors each hard rule removed."""
    eligible, rejected = hard_filter(contractors, req)
    return rank(eligible, req), rejected
