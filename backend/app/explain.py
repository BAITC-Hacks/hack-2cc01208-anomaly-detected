"""Per-card explanation generation.

The brief's core deliverable: "the value lies in the explanation, not the
sorting." Explanations must be grounded in the specific matched contractor
and request (never interchangeable, never generic filler like "a great
choice for your event").

Primary path: one LLM call per card, temperature=0 for determinism, given
only the real matched facts — no room for it to invent a reason. Falls back
to a template built from the same facts if the API call fails, so the demo
never goes blank for lack of API credit.
"""
from __future__ import annotations

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


_PROMPT = """Contractor: {name}
City: {city}
Starting price: {price:,} KZT
Event formats offered: {formats}
Languages: {languages}
Description (excerpt): {description}

Customer request: {event_type} event in {city}, on {date}, budget {budget:,} KZT{lang_line}{dur_line}

Write exactly 1-2 sentences explaining specifically why THIS contractor matches THIS request.
Cite concrete facts: budget headroom, format match, language match, or a specific detail from
the description. Do not use generic phrases like "a great choice for your event" or "perfect fit".
Do not invent facts not given above."""


def _llm_explain(row: pd.Series, req: MatchRequest) -> str:
    client = _get_client()
    prompt = _PROMPT.format(
        name=row["anon_name"],
        city=row["city"],
        price=int(row["price_from_kzt"]),
        formats=", ".join(row["event_formats"]),
        languages=", ".join(row["languages"]),
        description=row["description"][:400],
        event_type=req.event_type,
        date=req.date,
        budget=req.budget_kzt,
        lang_line=f", language {req.language}" if req.language else "",
        dur_line=f", duration {req.hours:.0f}h" if req.hours else "",
    )
    resp = client.chat.completions.create(
        model=config.CHAT_MODEL,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def _template_explain(row: pd.Series, req: MatchRequest) -> str:
    headroom = req.budget_kzt - row["price_from_kzt"]
    bits = [f"offers {req.event_type} events from {row['price_from_kzt']:,}₸"]
    if headroom > 0:
        bits.append(f"leaving {headroom:,}₸ of headroom against your {req.budget_kzt:,}₸ budget")
    if req.language and req.language in row["languages"]:
        bits.append(f"works in {req.language}")
    bits.append(f"is free on {req.date}")
    return f"{row['anon_name']} " + ", ".join(bits) + "."


def explain(row: pd.Series, req: MatchRequest) -> tuple[str, str]:
    """Returns (explanation_text, source) where source is 'llm' or 'template'."""
    try:
        return _llm_explain(row, req), "llm"
    except Exception:
        return _template_explain(row, req), "template"
