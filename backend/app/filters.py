"""Hard, deterministic filtering — no model involved.

Field names and the three status values follow docs/api.md exactly:
- found       -> 1-3 cards
- no_category -> that (city, category) combination doesn't exist at all
- none_fit    -> candidates exist in that city/category, but none pass
                 every filter

`excluded` (busy_on_date / over_budget / wrong_format / wrong_language /
too_few_hours) is computed for the whole city+category pool regardless of
outcome, per the contract's "excluded возвращается всегда (и при found
тоже)".
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

EXCLUSION_REASONS = ["busy_on_date", "over_budget", "wrong_format", "wrong_language", "too_few_hours"]


@dataclass
class MatchRequest:
    city: str
    date: str  # "YYYY-MM-DD"
    event_type: str
    category: str
    budget_kzt: int
    language: str | None = None
    hours: float | None = None


@dataclass
class RejectedCandidate:
    id: str
    name: str
    reasons: list[str]


@dataclass
class FilterResult:
    status: str  # "found" | "no_category" | "none_fit"
    survivors: pd.DataFrame
    rejected: list[RejectedCandidate] = field(default_factory=list)
    category_pool_size: int = 0
    excluded: dict[str, int] = field(default_factory=lambda: {k: 0 for k in EXCLUSION_REASONS})


def _tag_reasons(row: pd.Series, req: MatchRequest) -> list[str]:
    """Structured exclusion-reason tags (contract's `excluded` buckets),
    not human prose — those live in `_human_reasons` below."""
    tags = []
    if req.event_type not in row["event_formats"]:
        tags.append("wrong_format")
    if row["price_from_kzt"] > req.budget_kzt:
        tags.append("over_budget")
    if req.date in row["busy_dates"]:
        tags.append("busy_on_date")
    if req.language and req.language not in row["languages"]:
        tags.append("wrong_language")
    if req.hours is not None and pd.notna(row["max_hours"]) and row["max_hours"] < req.hours:
        tags.append("too_few_hours")
    return tags


_HUMAN_TEXT = {
    "wrong_format": lambda row, req: f"doesn't take the '{req.event_type}' format",
    "over_budget": lambda row, req: f"starting price {row['price_from_kzt']:,}₸ exceeds budget {req.budget_kzt:,}₸",
    "busy_on_date": lambda row, req: f"already booked on {req.date}",
    "wrong_language": lambda row, req: f"doesn't work in '{req.language}'",
    "too_few_hours": lambda row, req: f"max {row['max_hours']:.0f}h on site, request needs {req.hours:.0f}h",
}


def _human_reasons(row: pd.Series, req: MatchRequest, tags: list[str]) -> list[str]:
    return [_HUMAN_TEXT[tag](row, req) for tag in tags]


def filter_contractors(df: pd.DataFrame, req: MatchRequest) -> FilterResult:
    pool = df[(df["city"] == req.city) & (df["categories"].apply(lambda cats: req.category in cats))]

    if pool.empty:
        return FilterResult(status="no_category", survivors=pool, category_pool_size=0)

    tags_per_row = pool.apply(lambda row: _tag_reasons(row, req), axis=1)

    excluded = {k: 0 for k in EXCLUSION_REASONS}
    for tags in tags_per_row:
        for tag in tags:
            excluded[tag] += 1

    survives = tags_per_row.apply(len) == 0
    survivors = pool[survives].copy()

    if not survivors.empty:
        return FilterResult(status="found", survivors=survivors, category_pool_size=len(pool), excluded=excluded)

    rejected = [
        RejectedCandidate(id=row["id"], name=row["anon_name"], reasons=_human_reasons(row, req, tags_per_row[idx]))
        for idx, row in pool.iterrows()
    ]
    return FilterResult(
        status="none_fit", survivors=survivors, rejected=rejected, category_pool_size=len(pool), excluded=excluded
    )
