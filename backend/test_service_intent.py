"""Service intent in /api/match: say clearly when the asked-for service isn't there.

The matcher's ranking is never touched — these tests also prove that the
cards (ids, order) are identical with and without the service-intent layer.
"""

from __future__ import annotations

import json

from backend.test_api import client  # first: disables the real LLM before backend.main loads
from backend.frontend_api import build_response  # noqa: I001
from backend.main import CONTRACTORS, KNOWN_CATEGORIES, app, get_explainer
from backend.matcher import match, match_with_rejections
from backend.models import MatchRequest
from backend.relevance import requested_services
from backend.test_frontend_api import ALL_DATES, FRONT_VALID, _as_match_body, _match_ids
from backend.test_llm_explainer import answer, fake_explainer, ids_of
from backend.test_matcher import fixture_request, make_contractor

HOST_QUERY = "ведущий на той, чтобы говорил на казахском"
HOST_BASE = {"city": "Алматы", "event_type": "той", "budget_kzt": 600_000,
             "language": "казахский", "query": HOST_QUERY}
NO_HOST_DAY = "2026-11-07"  # every Almaty host is busy / wrong format / over budget
# Cheapest Almaty host doing "той" in Kazakh starts at 900 000 ₸, so at 600 000
# there is never a host; scenarios that need one use this budget instead.
HOST_AVAILABLE_BASE = {**HOST_BASE, "budget_kzt": 2_000_000}


def _front(body: dict) -> dict:
    r = client.post("/api/match", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _first_date(body: dict, predicate) -> tuple[str, dict]:
    for d in ALL_DATES:
        resp = _front({**body, "date": d})
        if predicate(resp):
            return d, resp
    raise AssertionError("no date in the dataset range satisfies the scenario")


# --------------------------------------------------------------------------

def test_detection_is_deterministic_and_specific():
    def detect(query):
        req = MatchRequest(city="Алматы", event_format="свадьба",
                           event_date="2026-10-10", query=query)
        return requested_services(req, KNOWN_CATEGORIES)

    assert detect("Нужен фотограф и видеограф на свадьбу") == ("видеограф", "фотограф")
    assert detect("ищем ведущего") == ("ведущий",)          # not "ведущий церемонии"
    assert "ведущий церемонии" in detect("ведущий церемонии регистрации")
    assert detect("нужна фотобудка") == ("фото и видеобудки",)
    assert detect("тамада и живая кавер группа") == ("ведущий", "лайв-бэнд")
    # explicit category is a hard filter, not an intent
    req = MatchRequest(city="Алматы", event_format="свадьба", event_date="2026-10-10",
                       category="Ведущий")
    assert requested_services(req, KNOWN_CATEGORIES) == ()


def test_host_available_normal_message():
    d, body = _first_date(HOST_AVAILABLE_BASE, lambda r: r["service_intent"]
                          and not r["service_intent"]["unavailable"] and r["cards"])
    intent = body["service_intent"]
    assert intent["requested"] == ["Ведущий"] and intent["unavailable"] == []
    first = body["cards"][0]
    assert first["alternative"] is False and "Ведущий" in first["category"]
    assert not first["explanation"].startswith("Альтернатива")
    assert "не нашлось" not in body["message"]
    for card in body["cards"]:  # alternative flag == "is not a host"
        assert card["alternative"] == ("Ведущий" not in card["category"]), (d, card)


def test_host_unavailable_says_so():
    body = _front({**HOST_BASE, "date": NO_HOST_DAY})
    assert body["status"] == "found" and body["cards"]  # alternatives may still appear
    assert body["service_intent"] == {
        "requested": ["Ведущий"], "unavailable": ["Ведущий"], "not_in_top": []}
    assert "не нашлось: «Ведущий»" in body["message"]
    assert "альтернатив" in body["message"]
    for card in body["cards"]:
        assert card["alternative"] is True
        assert "Ведущий" not in card["category"]
        assert card["explanation"].startswith("Альтернатива (не «Ведущий»): ")
    # ...and it is true: every Almaty host is out for this request
    req = MatchRequest(**_as_match_body({**HOST_BASE, "date": NO_HOST_DAY}))
    assert not [s for s in match(CONTRACTORS, req) if "ведущий" in s.contractor.categories]


def test_explicit_category_hard_filter_unchanged():
    # No host free that day -> the hard filter gives none_fit, not alternatives.
    body = _front({**HOST_BASE, "date": NO_HOST_DAY, "category": "Ведущий"})
    assert body["status"] == "none_fit" and body["cards"] == []
    assert body["service_intent"] is None
    # A day with hosts: only hosts, never flagged, same ids as /match.
    d, _ = _first_date(HOST_AVAILABLE_BASE, lambda r: r["service_intent"]
                       and not r["service_intent"]["unavailable"])
    front = {**HOST_AVAILABLE_BASE, "date": d, "category": "Ведущий"}
    body = _front(front)
    assert body["cards"] and body["service_intent"] is None
    for card in body["cards"]:
        assert card["category"] == "Ведущий" and card["alternative"] is False
    assert [c["id"] for c in body["cards"]] == _match_ids(front)[:3]


def test_multi_service_query():
    body = _front(FRONT_VALID)  # "Нужен фотограф и видеограф на свадьбу"
    assert [c["id"] for c in body["cards"]] == ["HK-30583", "HK-53108", "HK-62242"]
    assert body["service_intent"] == {
        "requested": ["Видеограф", "Фотограф"], "unavailable": [], "not_in_top": []}
    assert all(c["alternative"] is False for c in body["cards"])
    assert "не нашлось" not in body["message"]

    # A day with photographers but no videographer free: partial, not "nothing".
    base = {k: v for k, v in FRONT_VALID.items() if k != "date"}
    _, partial = _first_date(base, lambda r: r["service_intent"]["unavailable"] == ["Видеограф"])
    assert "Не нашлось: «Видеограф»" in partial["message"]
    assert "альтернатив" not in partial["message"]
    assert any(c["category"] == "Фотограф" and not c["alternative"] for c in partial["cards"])


def test_available_but_not_in_top3_fixture():
    # Controlled: 3 photographers outrank the only videographer (4th).
    pool = [make_contractor(f"FX-00{i}", ("Фотограф",), 100_000) for i in (1, 2, 3)]
    pool.append(make_contractor("FX-009", ("Видеограф",), 490_000, synthetic=True))
    req = fixture_request(query="фотограф и видеограф")
    ranked, rejected = match_with_rejections(pool, req)
    known = {"фотограф": "Фотограф", "видеограф": "Видеограф"}
    resp = build_response(ranked, rejected, req, known)
    assert [c.id for c in resp.cards] == ["FX-001", "FX-002", "FX-003"]
    assert resp.service_intent.unavailable == []
    assert resp.service_intent.not_in_top == ["Видеограф"]
    assert "Есть и «Видеограф», но не в первой тройке" in resp.message


def test_service_intent_never_changes_ids_or_order():
    queries = (HOST_QUERY, "фотограф и видеограф", "нужна фотобудка", "тамада",
               "цветы и декор", "хочу красивую свадьбу")
    for d in ALL_DATES[::11]:
        for q in queries:
            for event_type in ("свадьба", "той", "корпоратив"):
                front = {"city": "Алматы", "date": d, "event_type": event_type, "query": q}
                req = MatchRequest(**_as_match_body(front))
                ranked, rejected = match_with_rejections(CONTRACTORS, req)
                plain = build_response(ranked, rejected, req)             # layer off
                aware = build_response(ranked, rejected, req, KNOWN_CATEGORIES)
                assert [c.id for c in aware.cards] == [c.id for c in plain.cards]
                assert aware.status == plain.status and aware.excluded == plain.excluded
                assert [c.id for c in aware.cards] == _match_ids(front)[:3]


def test_groq_on_off_same_service_intent():
    body = {**HOST_BASE, "date": NO_HOST_DAY}
    off = _front(body)

    seen_flags = []

    def behavior(payload):
        seen_flags.extend(c.get("provides_requested_service")
                          for c in payload["contractors_in_final_order"])
        ids = ids_of(payload)
        # first text claims the wrong service, second already says "альтернатива"
        return answer([(ids[0], "Отлично проведёт ваш той."),
                       (ids[1], "Хорошая альтернатива на ваш той.")]
                      + [(i, "Свободен в эту дату.") for i in ids[2:]])

    explainer, _ = fake_explainer(behavior)
    app.dependency_overrides[get_explainer] = lambda: explainer
    try:
        r = client.post("/api/match", json=body)
    finally:
        app.dependency_overrides[get_explainer] = lambda: None
    on = r.json()
    assert r.headers["X-Explanations"] == "llm"
    for key in ("status", "message", "excluded", "service_intent"):
        assert on[key] == off[key], key
    assert [(c["id"], c["alternative"]) for c in on["cards"]] == \
           [(c["id"], c["alternative"]) for c in off["cards"]]
    assert seen_flags and all(flag is False for flag in seen_flags)  # LLM was told
    assert on["cards"][0]["explanation"].startswith("Альтернатива (не «Ведущий»): ")
    assert on["cards"][1]["explanation"] == "Хорошая альтернатива на ваш той."  # no double

    # No service intent -> the LLM payload carries no such flag at all.
    captured = []
    explainer, _ = fake_explainer(lambda p: captured.append(p) or answer(
        [(i, "Свободен в эту дату.") for i in ids_of(p)]))
    app.dependency_overrides[get_explainer] = lambda: explainer
    try:
        client.post("/api/match", json={**FRONT_VALID, "query": "хочу красивую свадьбу"})
    finally:
        app.dependency_overrides[get_explainer] = lambda: None
    assert captured and all("provides_requested_service" not in c
                            for c in captured[0]["contractors_in_final_order"])
    json.dumps(captured)  # payload stays plain JSON


def test_general_query_no_fake_intent():
    for q in ("хочу красивую свадьбу недорого", "что-нибудь интересное для гостей",
              "!!!", "свадьба в Алматы", "нужно на 50 человек", None):
        body = _front({"city": "Алматы", "date": "2026-10-10", "event_type": "свадьба",
                       "budget_kzt": 500_000, "query": q})
        assert body["service_intent"] is None, q
        assert all(c["alternative"] is False for c in body["cards"]), q
        assert all(not c["explanation"].startswith("Альтернатива") for c in body["cards"])
        assert "не нашлось" not in body["message"].lower()


SERVICE_TESTS = [
    ("Service detection specific + deterministic", test_detection_is_deterministic_and_specific),
    ("Host asked + host available -> normal", test_host_available_normal_message),
    ("Host asked + none available -> says so", test_host_unavailable_says_so),
    ("Explicit category=Ведущий unchanged", test_explicit_category_hard_filter_unchanged),
    ("Photographer + videographer handled", test_multi_service_query),
    ("Available but not in top 3 (fixture)", test_available_but_not_in_top3_fixture),
    ("Service intent never changes ids/order", test_service_intent_never_changes_ids_or_order),
    ("Groq ON/OFF: same intent/status/message", test_groq_on_off_same_service_intent),
    ("General query -> no fake intent", test_general_query_no_fake_intent),
]
