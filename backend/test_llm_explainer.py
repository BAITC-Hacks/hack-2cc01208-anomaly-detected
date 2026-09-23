"""Tests for the Groq explanation layer — with a FAKE client, never the real API.

What must hold whatever the LLM returns: same cards, same order, same fields;
only `explanation` text may change, and only for ids the matcher selected.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import groq
import httpx

from backend.test_api import client  # first: disables the real LLM before backend.main loads
from backend.llm_explainer import (  # noqa: I001
    SYSTEM_PROMPT,
    GroqExplainer,
    explainer_from_env,
)
from backend.main import CONTRACTORS, app, get_explainer
from backend.test_frontend_api import FRONT_VALID

BY_ID = {c.id: c for c in CONTRACTORS}
TOP3 = ["HK-30583", "HK-53108", "HK-62242"]  # matcher's order for FRONT_VALID


# --------------------------------------------------------------------------
# Fake Groq client
# --------------------------------------------------------------------------

class FakeCompletions:
    def __init__(self, behavior):
        self.behavior = behavior  # payload -> str (content) | Exception
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = json.loads(kwargs["messages"][1]["content"])
        result = self.behavior(payload)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result))])


def fake_explainer(behavior) -> tuple[GroqExplainer, FakeCompletions]:
    completions = FakeCompletions(behavior)
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return GroqExplainer(fake_client, model="fake-model"), completions


def call_api(behavior, body: dict = FRONT_VALID):
    explainer, completions = fake_explainer(behavior)
    app.dependency_overrides[get_explainer] = lambda: explainer
    try:
        r = client.post("/api/match", json=body)
    finally:
        app.dependency_overrides[get_explainer] = lambda: None
    assert r.status_code == 200, r.text
    return r, completions


def template_response(body: dict = FRONT_VALID) -> dict:
    r = client.post("/api/match", json=body)
    assert r.headers["X-Explanations"] == "template"
    return r.json()


def ids_of(payload: dict) -> list[str]:
    return [c["contractor_id"] for c in payload["contractors_in_final_order"]]


def good_text(cid: str) -> str:
    return f"Объяснение для {BY_ID[cid].anon_name}: подходит под ваш запрос."


def answer(entries: list[tuple[str, str]]) -> str:
    return json.dumps({"explanations": [
        {"contractor_id": cid, "explanation": text} for cid, text in entries]},
        ensure_ascii=False)


def good(payload: dict) -> str:
    return answer([(cid, good_text(cid)) for cid in ids_of(payload)])


def assert_same_except_explanations(got: dict, base: dict) -> None:
    assert [c["id"] for c in got["cards"]] == [c["id"] for c in base["cards"]]
    strip = lambda b: {**b, "cards": [{k: v for k, v in c.items() if k != "explanation"}  # noqa: E731
                                      for c in b["cards"]]}
    assert strip(got) == strip(base)


def assert_fallback(behavior) -> None:
    base = template_response()
    r, _ = call_api(behavior)
    assert r.headers["X-Explanations"] == "template"
    assert r.json() == base


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_llm_explanations_used():
    base = template_response()
    r, calls = call_api(good)
    body = r.json()
    assert r.headers["X-Explanations"] == "llm"
    assert [c["id"] for c in body["cards"]] == TOP3
    assert_same_except_explanations(body, base)
    for card in body["cards"]:
        assert card["explanation"].startswith(good_text(card["id"]))
    assert len(calls.calls) == 1


def test_llm_sees_only_selected_contractors():
    _, calls = call_api(good)
    kwargs = calls.calls[0]
    payload = json.loads(kwargs["messages"][1]["content"])
    assert ids_of(payload) == TOP3  # exactly the matcher's top 3, in order
    assert kwargs["messages"][0]["content"] == SYSTEM_PROMPT
    assert kwargs["response_format"] == {"type": "json_object"}
    for rule in ("MUST NOT", "change their order", "invent prices", "invent availability"):
        assert rule in SYSTEM_PROMPT


def test_llm_failure_falls_back():
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    for exc in (groq.APITimeoutError(request=req),
                groq.APIConnectionError(request=req),
                RuntimeError("boom")):
        assert_fallback(lambda payload, e=exc: e)


def test_llm_invalid_json_falls_back():
    for raw in ("", "   ", "not json", '{"explanations": ', "null", "[]",
                '{"foo": 1}', '{"explanations": []}', '{"explanations": "text"}',
                '{"explanations": ["just a string"]}'):
        assert_fallback(lambda payload, raw=raw: raw)
    assert_fallback(lambda payload: None)  # content=None


def test_llm_unknown_contractor_falls_back():
    assert_fallback(lambda p: answer([(cid, good_text(cid)) for cid in ids_of(p)]
                                     + [("HK-00000", "Выдуманный подрядчик.")]))
    assert_fallback(lambda p: answer([("HK-00000", "Выдуманный подрядчик.")]))


def test_llm_duplicate_ids_fall_back():
    assert_fallback(lambda p: answer([(cid, good_text(cid)) for cid in ids_of(p)]
                                     + [(TOP3[0], "Ещё раз.")]))


def test_llm_reverse_order_keeps_matcher_order():
    r, _ = call_api(lambda p: answer([(cid, good_text(cid)) for cid in reversed(ids_of(p))]))
    body = r.json()
    assert r.headers["X-Explanations"] == "llm"
    assert [c["id"] for c in body["cards"]] == TOP3
    for card in body["cards"]:  # matched by id, not by position
        assert card["explanation"].startswith(good_text(card["id"]))


def test_llm_cannot_add_fourth_contractor():
    base = template_response()
    fourth = next(x["contractor"]["id"] for x in client.post(
        "/match", json={"city": "Алматы", "event_format": "свадьба", "event_date": "2026-10-10",
                        "budget_kzt": 500_000, "query": FRONT_VALID["query"]},
        params={"limit": 4}).json()["results"][3:])
    assert fourth not in TOP3
    r, _ = call_api(lambda p: answer([(cid, good_text(cid)) for cid in ids_of(p)]
                                     + [(fourth, good_text(fourth))]))
    body = r.json()
    assert len(body["cards"]) == 3 and fourth not in [c["id"] for c in body["cards"]]
    assert body == base  # the whole answer was rejected


def test_llm_cannot_bring_in_busy_contractor():
    busy = [c.id for c in CONTRACTORS
            if c.city == "Алматы" and FRONT_VALID["date"] in c.busy_dates]
    assert busy
    for bad in busy:
        r, _ = call_api(lambda p, b=bad: answer([(b, "Лучший выбор, свободен в эту дату!")]))
        assert bad not in [c["id"] for c in r.json()["cards"]]
        assert r.json() == template_response()


def test_llm_missing_id_mixes_with_template():
    base = template_response()
    r, _ = call_api(lambda p: answer([(cid, good_text(cid)) for cid in ids_of(p)[:2]]))
    body = r.json()
    assert r.headers["X-Explanations"] == "mixed"
    assert [c["id"] for c in body["cards"]] == TOP3
    assert body["cards"][2]["explanation"] == base["cards"][2]["explanation"]
    assert body["cards"][0]["explanation"].startswith(good_text(TOP3[0]))


def test_llm_invented_number_rejected_per_card():
    base = template_response()

    def behavior(p):
        entries = [(cid, good_text(cid)) for cid in ids_of(p)]
        entries[0] = (entries[0][0], "Цена всего 99 000 ₸ и 15 лет опыта.")  # not in facts
        entries[1] = (entries[1][0], "Цена от 300 000 ₸, укладывается в бюджет 500 000 ₸.")
        return answer(entries)

    body = call_api(behavior)[0].json()
    assert body["cards"][0]["explanation"] == base["cards"][0]["explanation"]
    assert body["cards"][1]["explanation"].startswith("Цена от 300 000 ₸")


def test_llm_empty_or_huge_text_rejected_per_card():
    base = template_response()
    r, _ = call_api(lambda p: answer([(TOP3[0], ""), (TOP3[1], "Очень " * 300),
                                      (TOP3[2], good_text(TOP3[2]))]))
    body = r.json()
    assert r.headers["X-Explanations"] == "mixed"
    assert body["cards"][0]["explanation"] == base["cards"][0]["explanation"]
    assert body["cards"][1]["explanation"] == base["cards"][1]["explanation"]
    assert body["cards"][2]["explanation"].startswith(good_text(TOP3[2]))


def test_llm_disclosures_enforced():
    body = call_api(good)[0].json()
    for card in body["cards"]:
        c = BY_ID[card["id"]]
        assert ("оценочная" in card["explanation"]) == c.price_imputed
        assert ("синтетический" in card["explanation"]) == c.synthetic
    assert any(BY_ID[i].price_imputed for i in TOP3)  # the check above isn't vacuous


def test_llm_does_not_touch_match_endpoint_or_scores():
    body = {"city": "Алматы", "event_format": "свадьба", "event_date": "2026-10-10",
            "budget_kzt": 500_000, "query": FRONT_VALID["query"]}
    before = client.post("/match", json=body, params={"limit": 20}).json()
    explainer, calls = fake_explainer(good)
    app.dependency_overrides[get_explainer] = lambda: explainer
    try:
        after = client.post("/match", json=body, params={"limit": 20}).json()
    finally:
        app.dependency_overrides[get_explainer] = lambda: None
    assert before == after and calls.calls == []
    assert [x["contractor"]["id"] for x in after["results"]][:3] == TOP3


def test_llm_not_called_without_cards():
    none_fit = {"city": "Астана", "date": "2026-11-01", "event_type": "корпоратив",
                "budget_kzt": 1_000_000, "language": "английский"}
    r, calls = call_api(good, none_fit)
    assert r.json()["cards"] == [] and calls.calls == []
    assert r.headers["X-Explanations"] == "template"


def test_llm_result_cached():
    explainer, calls = fake_explainer(good)
    app.dependency_overrides[get_explainer] = lambda: explainer
    try:
        a = client.post("/api/match", json=FRONT_VALID).json()
        b = client.post("/api/match", json=FRONT_VALID).json()
    finally:
        app.dependency_overrides[get_explainer] = lambda: None
    assert a == b and len(calls.calls) == 1


def test_explainer_from_env_switch():
    keys = ("ENABLE_LLM_EXPLANATIONS", "GROQ_API_KEY")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        cases = [
            ({"ENABLE_LLM_EXPLANATIONS": "false", "GROQ_API_KEY": "gsk_test"}, False),
            ({"ENABLE_LLM_EXPLANATIONS": "true", "GROQ_API_KEY": ""}, False),
            ({"ENABLE_LLM_EXPLANATIONS": "true", "GROQ_API_KEY": "your_groq_api_key_here"}, False),
            ({"ENABLE_LLM_EXPLANATIONS": "true", "GROQ_API_KEY": "gsk_test"}, True),
        ]
        for env, enabled in cases:
            os.environ.update(env)
            assert (explainer_from_env() is not None) == enabled, env  # builds client, no call
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


LLM_TESTS = [
    ("LLM explanations used", test_llm_explanations_used),
    ("LLM sees only matcher's top 3", test_llm_sees_only_selected_contractors),
    ("LLM error/timeout -> template", test_llm_failure_falls_back),
    ("LLM invalid JSON -> template", test_llm_invalid_json_falls_back),
    ("LLM unknown contractor -> template", test_llm_unknown_contractor_falls_back),
    ("LLM duplicate ids -> template", test_llm_duplicate_ids_fall_back),
    ("LLM reversed order -> matcher order kept", test_llm_reverse_order_keeps_matcher_order),
    ("LLM cannot add a 4th contractor", test_llm_cannot_add_fourth_contractor),
    ("LLM cannot bring in busy contractor", test_llm_cannot_bring_in_busy_contractor),
    ("LLM missing id -> mixed", test_llm_missing_id_mixes_with_template),
    ("LLM invented number rejected", test_llm_invented_number_rejected_per_card),
    ("LLM empty/huge text rejected", test_llm_empty_or_huge_text_rejected_per_card),
    ("LLM disclosures enforced", test_llm_disclosures_enforced),
    ("LLM leaves /match and scores alone", test_llm_does_not_touch_match_endpoint_or_scores),
    ("LLM not called without cards", test_llm_not_called_without_cards),
    ("LLM result cached", test_llm_result_cached),
    ("ENABLE_LLM_EXPLANATIONS switch", test_explainer_from_env_switch),
]
