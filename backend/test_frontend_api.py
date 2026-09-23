"""Tests for the frontend adapter POST /api/match (contract: docs/api.md).

The key property: /api/match is a translator. For equivalent requests it must
return exactly /match's first 3 contractor IDs, in the same order.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.test_api import client  # first: disables the real LLM before backend.main loads
from backend.frontend_api import EXCLUDED_KEYS, MAX_CARDS  # noqa: I001
from backend.main import CONTRACTORS
from backend.matcher import match_with_rejections
from backend.models import MatchRequest

BY_ID = {c.id: c for c in CONTRACTORS}
ALL_DATES = [(date(2026, 9, 23) + timedelta(days=i)).isoformat() for i in range(101)]

FRONT_VALID = {
    "city": "Алматы",
    "date": "2026-10-10",
    "event_type": "свадьба",
    "budget_kzt": 500_000,
    "query": "Нужен фотограф и видеограф на свадьбу",
}


def _front(body: dict):
    return client.post("/api/match", json=body)


def _as_match_body(front: dict) -> dict:
    """The equivalent /match request (docs/api.md names -> MatchRequest names)."""
    rename = {"date": "event_date", "event_type": "event_format", "hours": "duration_hours"}
    return {rename.get(k, k): v for k, v in front.items()}


def _match_ids(front: dict) -> list[str]:
    r = client.post("/match", json=_as_match_body(front), params={"limit": 20})
    assert r.status_code == 200, r.text
    return [x["contractor"]["id"] for x in r.json()["results"]]


def _card_ids(front: dict) -> list[str]:
    r = _front(front)
    assert r.status_code == 200, r.text
    return [c["id"] for c in r.json()["cards"]]


def _equivalent_requests():
    for city in ("Алматы", "Астана"):
        for event_type in ("свадьба", "корпоратив", "той"):
            for d in ALL_DATES[::9]:
                for extra in (
                    {},
                    {"budget_kzt": 400_000},
                    {"query": "фотограф и видеограф"},
                    {"category": "Ведущий", "budget_kzt": 1_000_000},
                    {"language": "казахский", "hours": 5, "query": "ведущий тамада"},
                ):
                    yield {"city": city, "date": d, "event_type": event_type, **extra}


def test_front_contract_shape():
    r = _front(FRONT_VALID)
    assert r.status_code == 200, r.text
    body = r.json()
    # docs/api.md keys + documented extensions
    assert set(body) == {"status", "message", "cards", "excluded", "service_intent",
                         "interpreted_intent"}
    assert body["status"] == "found" and body["message"]
    assert set(body["excluded"]) == {
        "busy_on_date", "over_budget", "wrong_format", "wrong_language", "too_few_hours"}
    for card in body["cards"]:
        # docs/api.md keys + documented extension "alternative"
        assert set(card) == {"id", "name", "category", "city", "price_from_kzt",
                             "synthetic", "explanation", "alternative"}
        assert isinstance(card["category"], str) and card["explanation"]


def test_front_same_order_as_match():
    # The headline case.
    assert _card_ids(FRONT_VALID) == ["HK-30583", "HK-53108", "HK-62242"]
    assert _match_ids(FRONT_VALID)[:3] == ["HK-30583", "HK-53108", "HK-62242"]
    # And every equivalent request in a broad grid.
    checked = 0
    for front in _equivalent_requests():
        assert _card_ids(front) == _match_ids(front)[:MAX_CARDS], front
        checked += 1
    assert checked > 100


def test_front_never_busy_over_budget_wrong_city():
    for city in ("Алматы", "Астана"):
        for d in ALL_DATES:
            for budget in (None, 300_000):
                front = {"city": city, "date": d, "event_type": "свадьба", "budget_kzt": budget}
                r = _front(front)
                assert r.status_code == 200, r.text
                for card in r.json()["cards"]:
                    c = BY_ID[card["id"]]
                    assert d not in c.busy_dates, (d, c.id)
                    assert c.city == city == card["city"], (city, c.id)
                    if budget is not None:
                        assert card["price_from_kzt"] <= budget


def test_front_invalid_input_422():
    for bad_date in ("2026-13-01", "2026-02-30", "10.10.2026", "20261010", ""):
        assert _front({**FRONT_VALID, "date": bad_date}).status_code == 422, bad_date
    for bad_budget in (0, -1):
        assert _front({**FRONT_VALID, "budget_kzt": bad_budget}).status_code == 422
    for bad_hours in (0, -3):
        assert _front({**FRONT_VALID, "hours": bad_hours}).status_code == 422
    for missing in ("city", "date", "event_type"):
        body = {k: v for k, v in FRONT_VALID.items() if k != missing}
        assert _front(body).status_code == 422, missing
    # /match field names are NOT the frontend contract
    assert _front(_as_match_body(FRONT_VALID)).status_code == 422


def test_front_max_three_cards():
    many = {"city": "Алматы", "date": "2026-10-10", "event_type": "свадьба"}
    assert len(_match_ids(many)) > MAX_CARDS
    body = _front(many).json()
    assert body["status"] == "found" and len(body["cards"]) == MAX_CARDS
    assert "показаны 3" in body["message"]
    for front in _equivalent_requests():
        assert len(_front(front).json()["cards"]) <= MAX_CARDS


def test_front_status_no_category():
    body = _front({"city": "Астана", "date": "2026-10-10", "event_type": "свадьба",
                   "category": "Ресторан"}).json()   # Ресторан exists only in Алматы
    assert body["status"] == "no_category" and body["cards"] == []
    assert "Ресторан" in body["message"]
    assert sum(body["excluded"].values()) == 0


def test_front_status_none_fit():
    body = _front({"city": "Астана", "date": "2026-11-01", "event_type": "корпоратив",
                   "budget_kzt": 1_000_000, "language": "английский"}).json()
    assert body["status"] == "none_fit" and body["cards"] == []
    astana = sum(1 for c in CONTRACTORS if c.city == "Астана")
    assert sum(body["excluded"].values()) == astana  # every candidate accounted for
    assert body["message"].startswith("Никто из")


def test_front_found_fewer_than_three_explains():
    seen = 0
    for front in _equivalent_requests():
        body = _front(front).json()
        if body["status"] == "found" and len(body["cards"]) < MAX_CARDS:
            assert body["message"].startswith(("Подходят только", "Всего")), body["message"]
            seen += 1
    assert seen > 0, "grid never produced a 1-2 card result"


def test_front_excluded_matches_core():
    for front in list(_equivalent_requests())[::7]:
        body = _front(front).json()
        _, rejected = match_with_rejections(CONTRACTORS, MatchRequest(**_as_match_body(front)))
        expected = {key: rejected.get(reason, 0) for reason, key in EXCLUDED_KEYS.items()}
        assert body["excluded"] == expected, front


def test_front_explanation_is_factual():
    front = {**FRONT_VALID, "hours": 6, "language": "русский"}
    body = _front(front).json()
    assert body["cards"]
    for card in body["cards"]:
        c, text = BY_ID[card["id"]], card["explanation"]
        assert "10.10.2026" in text
        assert f"{c.price_from_kzt:,}".replace(",", " ") in text
        assert ("синтетический" in text) == c.synthetic
        assert ("оценочная" in text) == c.price_imputed
        if c.max_hours is None:
            assert "не указана" in text


def test_front_deterministic():
    assert _front(FRONT_VALID).json() == _front(FRONT_VALID).json()


FRONTEND_TESTS = [
    ("/api/match contract shape", test_front_contract_shape),
    ("/api/match same order as /match", test_front_same_order_as_match),
    ("/api/match never busy/over budget/wrong city", test_front_never_busy_over_budget_wrong_city),
    ("/api/match invalid input -> 422", test_front_invalid_input_422),
    ("/api/match max 3 cards", test_front_max_three_cards),
    ("/api/match status no_category", test_front_status_no_category),
    ("/api/match status none_fit", test_front_status_none_fit),
    ("/api/match <3 cards explained", test_front_found_fewer_than_three_explains),
    ("/api/match excluded == core counts", test_front_excluded_matches_core),
    ("/api/match explanations factual", test_front_explanation_is_factual),
    ("/api/match deterministic", test_front_deterministic),
]
