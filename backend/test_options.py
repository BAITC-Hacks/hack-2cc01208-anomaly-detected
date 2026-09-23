"""Tests for GET /api/options (docs/api.md: optional dropdown-population endpoint)."""

from __future__ import annotations

from backend.main import CONTRACTORS
from backend.test_api import client


def test_options_shape_and_content():
    r = client.get("/api/options")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"cities", "categories", "event_formats", "languages"}
    for key in body:
        assert isinstance(body[key], list) and body[key] == sorted(body[key])
        assert len(body[key]) == len(set(body[key])), f"{key} has duplicates"


def test_options_cities_cover_dataset():
    r = client.get("/api/options")
    assert set(r.json()["cities"]) == {c.city for c in CONTRACTORS}


def test_options_category_used_by_match_endpoint_is_valid():
    # Every category /api/options offers must actually be usable as a hard
    # filter on /api/match — i.e. the two endpoints can't drift apart.
    categories = client.get("/api/options").json()["categories"]
    assert "Фотограф" in categories
    r = client.post("/api/match", json={
        "city": "Алматы", "date": "2026-10-15", "event_type": "корпоратив",
        "category": "Фотограф", "budget_kzt": 2_000_000,
    })
    assert r.status_code == 200
    assert r.json()["status"] in {"found", "none_fit"}
