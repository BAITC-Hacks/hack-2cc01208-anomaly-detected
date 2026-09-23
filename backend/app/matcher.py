"""Orchestrates filter -> rank -> explain into the exact response shape
defined by docs/api.md.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .explain import explain
from .filters import EXCLUSION_REASONS, MatchRequest, filter_contractors
from .ranking import rank


def match(df: pd.DataFrame, req: MatchRequest) -> dict:
    result = filter_contractors(df, req)

    if result.status == "no_category":
        return {
            "status": "no_category",
            "message": f"There is no '{req.category}' category in {req.city} in this catalog.",
            "cards": [],
            "excluded": {k: 0 for k in EXCLUSION_REASONS},
        }

    if result.status == "none_fit":
        return {
            "status": "none_fit",
            "message": (
                f"Found {result.category_pool_size} '{req.category}' contractor(s) in {req.city}, "
                f"but none meet all your conditions."
            ),
            "cards": [],
            "excluded": result.excluded,
        }

    ranked = rank(result.survivors, req)
    rows = [row for _, row in ranked.iterrows()]

    # Each explain() call is an independent blocking network request (one
    # LLM call per card) — running them concurrently instead of in sequence
    # is what keeps 3-card responses comfortably under the brief's 10s
    # target instead of merely under it.
    with ThreadPoolExecutor(max_workers=max(len(rows), 1)) as pool:
        explanations = list(pool.map(lambda row: explain(row, req), rows))

    cards = []
    for row, (text, source) in zip(rows, explanations):
        cards.append({
            "id": row["id"],
            "name": row["anon_name"],
            "category": req.category,
            "city": row["city"],
            "price_from_kzt": int(row["price_from_kzt"]),
            "synthetic": bool(row.get("synthetic", False)),
            "explanation": text,
            "explanation_source": source,
            "relevance": round(float(row["relevance"]), 4),
            "ranking_method": row["ranking_method"],
        })

    shown = len(cards)
    message = f"Found {shown} matching contractor(s)" + (
        f" out of {result.category_pool_size} in this category/city." if shown < 3 else "."
    )
    return {
        "status": "found",
        "message": message,
        "cards": cards,
        "excluded": result.excluded,
    }
