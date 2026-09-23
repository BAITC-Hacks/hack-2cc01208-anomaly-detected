"""Runs the demo queries the brief explicitly asks to be shown:

  1. A busy category on an autumn date, where ranking actually matters
     (Ведущий=15, Фотограф=12, Банкетный зал=8 profiles).
  2. A rare category (Флорист, Декоратор, etc. — 3 profiles each).
  3. A query with no results.

Plus two extra sanity checks: a venue category (the brief's own "find a
hall" example) and a query that exercises the language + hours filters.

Usage: python demo_queries.py
"""
from __future__ import annotations

from app.data_loader import load_contractors
from app.filters import MatchRequest
from app.matcher import match

df = load_contractors()

QUERIES = {
    "1) Dense category, autumn date (ranking matters)": MatchRequest(
        city="Алматы", date="2026-10-15", event_type="корпоратив",
        category="Фотограф", budget_kzt=2_000_000, language="русский",
    ),
    "2) Rare category (3 profiles)": MatchRequest(
        city="Алматы", date="2026-10-20", event_type="свадьба",
        category="Флорист", budget_kzt=500_000,
    ),
    "3) No-result query": MatchRequest(
        city="Астана", date="2026-12-24", event_type="той",
        category="Отель", budget_kzt=50_000,  # deliberately unrealistic budget in a peak December slot
    ),
    "4) Venue category (same pipeline, brief's own example)": MatchRequest(
        city="Алматы", date="2026-11-14", event_type="свадьба",
        category="Банкетный зал", budget_kzt=5_000_000,
    ),
    "5) Language + duration filters exercised": MatchRequest(
        city="Алматы", date="2026-10-15", event_type="корпоратив",
        category="Ведущий", budget_kzt=5_000_000, language="английский", hours=9,
    ),
}


def main():
    for label, req in QUERIES.items():
        print("=" * 100)
        print(label)
        print(f"  request: {req}")
        result = match(df, req)
        print(f"  status: {result['status']}")
        print(f"  message: {result['message']}")
        for card in result["cards"]:
            print(f"    - {card['name']} ({card['price_from_kzt']:,}₸) [{card['explanation_source']}]")
            print(f"      {card['explanation']}")
        print(f"  excluded breakdown: {result['excluded']}")
        print()


if __name__ == "__main__":
    main()
