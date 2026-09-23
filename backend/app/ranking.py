"""Semantic ranking of the (already hard-filtered) survivors.

Reuses the same embed + cosine-similarity pattern as
`agent-kit/python/agent_kit/rag.py`, just pointed at each contractor's free-
text `description` instead of document chunks, and ranking the request's own
text against it.

Falls back to a deterministic, non-AI heuristic (closeness of price to
budget) if the OpenAI call fails for any reason (no key, no quota, network) —
the brief's determinism requirement has to hold either way, and a hackathon
demo can't depend on a live API call succeeding.
"""
from __future__ import annotations

import math

import pandas as pd

from . import config
from .filters import MatchRequest

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _request_text(req: MatchRequest) -> str:
    parts = [f"{req.event_type} event in {req.city}", f"category {req.category}", f"budget {req.budget_kzt} KZT"]
    if req.language:
        parts.append(f"language {req.language}")
    if req.hours:
        parts.append(f"duration {req.hours}h")
    return ", ".join(parts)


def _embed_rank(survivors: pd.DataFrame, req: MatchRequest) -> pd.DataFrame:
    client = _get_client()
    query = _request_text(req)
    query_vec = client.embeddings.create(model=config.EMBEDDING_MODEL, input=[query]).data[0].embedding
    desc_resp = client.embeddings.create(model=config.EMBEDDING_MODEL, input=survivors["description"].tolist())
    scores = [_cosine(query_vec, item.embedding) for item in desc_resp.data]
    return survivors.assign(relevance=scores, ranking_method="semantic_embedding")


def _fallback_rank(survivors: pd.DataFrame, req: MatchRequest) -> pd.DataFrame:
    # Deterministic, no-AI proxy: prefer contractors whose starting price
    # leaves the most budget headroom (closer to, but under, budget reads as
    # a better fit than a contractor far under budget with less to offer).
    fit = 1 - ((req.budget_kzt - survivors["price_from_kzt"]) / max(req.budget_kzt, 1))
    return survivors.assign(relevance=fit, ranking_method="budget_fit_fallback")


def rank(survivors: pd.DataFrame, req: MatchRequest, top_k: int = config.MAX_CARDS) -> pd.DataFrame:
    if survivors.empty:
        return survivors

    try:
        ranked = _embed_rank(survivors, req)
    except Exception:
        ranked = _fallback_rank(survivors, req)

    # id tiebreak keeps ordering deterministic even if two scores land equal
    ranked = ranked.sort_values(["relevance", "id"], ascending=[False, True])
    return ranked.head(top_k).reset_index(drop=True)
