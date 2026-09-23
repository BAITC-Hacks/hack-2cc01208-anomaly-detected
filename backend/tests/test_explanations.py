"""Definition-of-Done check: 'with the names erased, the cards of one
request cannot be confused with each other' — i.e. explanations must not
collapse to interchangeable boilerplate.
"""
from app.data_loader import load_contractors
from app.filters import MatchRequest
from app.matcher import match

df = load_contractors()


def _erase_names(text: str, cards: list[dict]) -> str:
    for card in cards:
        text = text.replace(card["name"], "<NAME>")
    return text


def test_multi_card_explanations_are_not_interchangeable():
    req = MatchRequest(city="Алматы", date="2026-10-15", event_type="корпоратив",
                        category="Ведущий", budget_kzt=5_000_000)
    result = match(df, req)
    assert result["status"] == "found"
    cards = result["cards"]
    assert len(cards) >= 2, "need at least 2 cards for this check to mean anything"

    scrubbed = [_erase_names(card["explanation"], cards) for card in cards]
    assert len(set(scrubbed)) == len(scrubbed), (
        "two cards have identical explanations even after removing names — "
        "they'd be confusable to a user"
    )
