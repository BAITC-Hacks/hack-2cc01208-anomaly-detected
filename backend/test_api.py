"""API tests (FastAPI TestClient, no server needed).

    python -m backend.test_matcher      # runs these too
    python -m pytest backend            # or via pytest
"""

from __future__ import annotations

import os
import warnings
from datetime import date, timedelta

# Never call the real Groq API from tests (also set in conftest.py for pytest;
# repeated here for `python -m backend.test_matcher`). Must precede backend.main.
os.environ["ENABLE_LLM_EXPLANATIONS"] = "false"
os.environ["ENABLE_LLM_INTENT"] = "false"

# Starlette suggests the "httpx2" package; plain httpx works fine for tests.
warnings.filterwarnings("ignore", message=r"Using `httpx` with `starlette.testclient`")
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import (  # noqa: E402
    CONTRACTORS,
    MAX_LIMIT,
    app,
    get_explainer,
    get_intent_parser,
)
from backend.matcher import match  # noqa: E402
from backend.models import MatchRequest  # noqa: E402

# Belt and braces: even LLM helpers built at import are replaced by "none".
app.dependency_overrides[get_explainer] = lambda: None
app.dependency_overrides[get_intent_parser] = lambda: None
client = TestClient(app)
BY_ID = {c.id: c for c in CONTRACTORS}

VALID = {
    "city": "Алматы",
    "event_format": "свадьба",
    "event_date": "2026-10-10",
    "budget_kzt": 500_000,
    "query": "Нужен фотограф и видеограф на свадьбу",
}

ALL_DATES = [(date(2026, 9, 23) + timedelta(days=i)).isoformat() for i in range(101)]


def _post(body: dict, **params):
    return client.post("/match", json=body, params=params)


def test_api_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "contractors_loaded": 66}


def test_api_match_valid():
    r = _post(VALID)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"request", "eligible_count", "excluded", "results"}
    assert body["eligible_count"] >= len(body["results"]) > 0
    first = body["results"][0]
    assert set(first) == {"contractor", "score", "score_breakdown"}
    assert first["score"] == first["score_breakdown"]["total"]
    assert "busy_dates" not in first["contractor"]
    # API returns exactly the core matcher's order (no logic duplicated in main.py)
    core = [s.contractor.id for s in match(CONTRACTORS, MatchRequest(**VALID))][:5]
    assert [x["contractor"]["id"] for x in body["results"]] == core


def test_api_never_returns_busy_or_over_budget():
    for d in ALL_DATES:
        for budget in (None, 300_000, 1_000_000):
            body = {**VALID, "event_date": d, "budget_kzt": budget}
            r = _post(body, limit=MAX_LIMIT)
            assert r.status_code == 200, r.text
            for res in r.json()["results"]:
                c = BY_ID[res["contractor"]["id"]]
                assert d not in c.busy_dates, (d, c.id)
                if budget is not None:
                    assert res["contractor"]["price_from_kzt"] <= budget


def test_api_limit():
    req = {k: v for k, v in VALID.items() if k != "budget_kzt"}
    total = _post(req, limit=MAX_LIMIT).json()["eligible_count"]
    assert total > 5, "fixture request should have more than 5 eligible"
    assert len(_post(req).json()["results"]) == 5  # default
    for limit in (1, 3, 5, MAX_LIMIT):
        body = _post(req, limit=limit).json()
        assert len(body["results"]) == min(limit, total)
        assert body["eligible_count"] == total


def test_api_invalid_date_422():
    for bad in ("2026-13-01", "2026-02-30", "10.10.2026", "20261010", "2026-W41-6", ""):
        assert _post({**VALID, "event_date": bad}).status_code == 422, bad


def test_api_invalid_budget_422():
    for bad in (-1, 0, "много"):
        assert _post({**VALID, "budget_kzt": bad}).status_code == 422, bad


def test_api_invalid_duration_422():
    for bad in (0, -2):
        assert _post({**VALID, "duration_hours": bad}).status_code == 422, bad


def test_api_limit_out_of_range_422():
    for bad in (MAX_LIMIT + 1, 0, -1):
        assert _post(VALID, limit=bad).status_code == 422, bad


def test_api_zero_eligible_is_not_error():
    # Proven 0 on the current CSV; without the budget, HK-90012 would qualify.
    r = _post({"city": "Астана", "event_format": "корпоратив", "event_date": "2026-11-01",
               "budget_kzt": 1_000_000, "language": "английский"})
    assert r.status_code == 200
    body = r.json()
    assert body["eligible_count"] == 0 and body["results"] == []
    assert sum(body["excluded"].values()) == 66


def test_api_deterministic():
    a, b = _post(VALID, limit=MAX_LIMIT).json(), _post(VALID, limit=MAX_LIMIT).json()
    pick = lambda body: [(x["contractor"]["id"], x["score"]) for x in body["results"]]  # noqa: E731
    assert pick(a) == pick(b) and pick(a)
    assert a == b


API_TESTS = [
    ("API /health", test_api_health),
    ("API /match valid request", test_api_match_valid),
    ("API never returns busy / over-budget", test_api_never_returns_busy_or_over_budget),
    ("API limit", test_api_limit),
    ("API invalid date -> 422", test_api_invalid_date_422),
    ("API invalid budget -> 422", test_api_invalid_budget_422),
    ("API invalid duration -> 422", test_api_invalid_duration_422),
    ("API limit out of range -> 422", test_api_limit_out_of_range_422),
    ("API 0 eligible -> 200 + empty", test_api_zero_eligible_is_not_error),
    ("API deterministic", test_api_deterministic),
]
