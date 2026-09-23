"""Pydantic models for match requests and contractor records."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_event_date(v: str) -> str:
    """Strictly YYYY-MM-DD (date.fromisoformat alone also takes "20261010",
    "2026-W41-6", ...) and a real calendar date. Returns the canonical form."""
    v = v.strip()
    if not _ISO_DATE.fullmatch(v):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(v).isoformat()


def normalize_text(value: object) -> str:
    """Lowercase, trim and collapse internal whitespace. Missing/NaN -> ""."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    return " ".join(str(value).split()).lower()


class MatchRequest(BaseModel):
    """What the event organizer is looking for."""

    model_config = ConfigDict(frozen=True)

    city: str
    event_format: str
    event_date: str  # ISO date, YYYY-MM-DD
    budget_kzt: int | None = Field(default=None, gt=0)
    category: str | None = None
    language: str | None = None
    duration_hours: float | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, max_length=1000)  # free-text need
    # Services (dataset category names) the need is known to ask for, e.g. from
    # the validated AI intent parser. Soft: they count as a category match in
    # relevance, never as a filter. None/empty = behave exactly as without it.
    services: tuple[str, ...] | None = Field(default=None, max_length=10)

    @field_validator("event_date")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        return parse_event_date(v)

    @field_validator("city", "event_format")
    @classmethod
    def _required_text(cls, v: str) -> str:
        if not normalize_text(v):
            raise ValueError("must not be empty")
        return v

    @field_validator("category", "language", "query")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return v if v is not None and normalize_text(v) else None


class Contractor(BaseModel):
    """One row of the organizers' dataset, parsed and normalized.

    Display fields (`anon_name`, `city`, `categories_display`) keep the original
    spelling; list fields used for matching are normalized (lowercase, trimmed).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    anon_name: str
    categories: tuple[str, ...]           # normalized
    categories_display: tuple[str, ...]   # original spelling
    city: str
    city_norm: str
    city_imputed: bool
    synthetic: bool
    price_from_kzt: int
    price_imputed: bool
    event_formats: tuple[str, ...]        # normalized
    languages: tuple[str, ...]            # normalized
    max_hours: float | None               # None = not specified in dataset
    busy_dates: frozenset[str]            # ISO dates when contractor is UNAVAILABLE
    description: str


class ScoreBreakdown(BaseModel):
    """Every component is 0..1 before weighting; `total` is the weighted sum.

    mode = "relevance"  when the request states a need (query and/or category)
    mode = "structured" when it doesn't (only budget + data confidence apply)
    """

    model_config = ConfigDict(frozen=True)

    mode: str
    relevance: float
    category_match: float
    description_overlap: float
    budget: float
    confidence: float
    specialization: float
    total: float
    matched_categories: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()


class ScoredContractor(BaseModel):
    model_config = ConfigDict(frozen=True)

    contractor: Contractor
    score: ScoreBreakdown
