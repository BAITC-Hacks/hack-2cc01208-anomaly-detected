"""AI intent parser — with a FAKE Groq client, never the real API.

The model's answers are scripted per test; what's under test is everything
Python does with them: validation against the dataset, explicit-field
priority, fallback, caching, and that ranking stays the matcher's.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import groq
import httpx

from backend.test_api import client  # first: disables the real LLM before backend.main loads
from backend.data_loader import known_values  # noqa: I001
from backend.intent_parser import IntentParser, intent_parser_from_env, validate_intent
from backend.main import CONTRACTORS, KNOWN, app, get_intent_parser
from backend.test_frontend_api import FRONT_VALID, _as_match_body

REFERENCE_IDS = ["HK-30583", "HK-53108", "HK-62242"]


# --------------------------------------------------------------------------
# Fake Groq
# --------------------------------------------------------------------------

class FakeIntentLLM:
    def __init__(self, behavior):
        self.behavior = behavior  # query text -> dict | str | Exception
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.behavior(kwargs["messages"][1]["content"])
        if isinstance(result, Exception):
            raise result
        content = result if isinstance(result, str) or result is None else json.dumps(
            result, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def intent(services=(), language=None, required=False, event_format=None, **extra) -> dict:
    return {"services": list(services), "language": language,
            "language_required": required, "event_format": event_format, **extra}


def parser_for(behavior) -> tuple[IntentParser, FakeIntentLLM]:
    llm = FakeIntentLLM(behavior)
    return IntentParser(llm, KNOWN, model="fake-model"), llm


def call(body: dict, behavior=None):
    """POST /api/match with a fake parser (behavior=None -> parser disabled)."""
    llm = None
    if behavior is not None:
        parser, llm = parser_for(behavior)
        app.dependency_overrides[get_intent_parser] = lambda: parser
    try:
        r = client.post("/api/match", json=body)
    finally:
        app.dependency_overrides[get_intent_parser] = lambda: None
    assert r.status_code == 200, r.text
    return r.json(), llm


def match_ids(body: dict) -> list[str]:
    r = client.post("/match", json=body, params={"limit": 20})
    assert r.status_code == 200, r.text
    return [x["contractor"]["id"] for x in r.json()["results"]]


def match_scores(body: dict) -> list[tuple[str, float]]:
    r = client.post("/match", json=body, params={"limit": 20})
    return [(x["contractor"]["id"], x["score"]) for x in r.json()["results"]]


def ids(body: dict) -> list[str]:
    return [c["id"] for c in body["cards"]]


def parse(text: str, answer) -> object:
    parser, _ = parser_for(lambda q: answer)
    return parser.parse(text)


# --------------------------------------------------------------------------
# Extraction + validation
# --------------------------------------------------------------------------

def test_simple_service():
    p = parse("Нужен фотограф", intent(["Фотограф"]))
    assert p.services == ("Фотограф",) and p.language is None and p.event_format is None


def test_multiple_services():
    p = parse("Нужен фотограф и видеограф", intent(["Фотограф", "видеограф"]))
    assert p.services == ("Видеограф", "Фотограф")  # dataset spelling, sorted


def test_language_extraction():
    p = parse("Нужен фотограф который говорит по-казахски",
              intent(["Фотограф"], "Казахский", required=True))
    assert p.language == "казахский" and p.language_required is True
    weak = parse("желательно по-казахски", intent(language="казахский", required=False))
    assert weak.language == "казахский" and weak.language_required is False


def test_event_extraction():
    p = parse("Нужен фотограф на свадьбу", intent(["Фотограф"], event_format="Свадьба"))
    assert p.event_format == "свадьба"


def test_unknown_values_rejected():
    p = parse("дрон", intent(["Luxury Drone Master", "Super Photographer", "Фотограф"],
                             "клингонский", True, "бар-мицва"))
    assert p.services == ("Фотограф",)
    assert p.language is None and p.language_required is False and p.event_format is None
    # every surviving value exists in the dataset
    k = known_values(CONTRACTORS)
    assert set(p.services) <= set(k.categories.values())


def test_malformed_answers_raise():
    for raw in ("", "not json", "[]", '"text"', '{"services": "Фотограф"}',
                '{"services": [1, 2]}', '{"language": 5}', '{"language_required": "yes"}'):
        try:
            validate_intent(raw, KNOWN)
        except ValueError:
            continue
        raise AssertionError(f"accepted malformed {raw!r}")


# --------------------------------------------------------------------------
# Fallback
# --------------------------------------------------------------------------

def _assert_deterministic_fallback(behavior):
    body = {**FRONT_VALID}
    baseline, _ = call(body)                      # parser disabled
    got, llm = call(body, behavior)
    assert llm.calls, "parser was not even asked"
    assert got["interpreted_intent"]["source"] == "deterministic"
    assert got["interpreted_intent"]["services"] == ["Видеограф", "Фотограф"]
    assert got == baseline                        # exactly the existing system


def test_invalid_json_falls_back():
    for raw in ("not json", "", None, '{"services": "Фотограф"}'):
        _assert_deterministic_fallback(lambda q, raw=raw: raw)


def test_timeout_and_errors_fall_back():
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    for exc in (groq.APITimeoutError(request=req), groq.APIConnectionError(request=req),
                RuntimeError("boom")):
        _assert_deterministic_fallback(lambda q, e=exc: e)


def test_no_api_key_falls_back():
    saved = {k: os.environ.get(k) for k in ("ENABLE_LLM_INTENT", "GROQ_API_KEY",
                                           "ENABLE_LLM_EXPLANATIONS")}
    try:
        os.environ.update({"ENABLE_LLM_INTENT": "true", "GROQ_API_KEY": ""})
        assert intent_parser_from_env(KNOWN) is None
        os.environ["GROQ_API_KEY"] = "your_groq_api_key_here"
        assert intent_parser_from_env(KNOWN) is None
        os.environ.update({"ENABLE_LLM_INTENT": "false", "GROQ_API_KEY": "gsk_test"})
        assert intent_parser_from_env(KNOWN) is None
        os.environ["ENABLE_LLM_INTENT"] = "true"
        assert intent_parser_from_env(KNOWN) is not None  # builds a client, no call
        # unset -> follows ENABLE_LLM_EXPLANATIONS
        del os.environ["ENABLE_LLM_INTENT"]
        os.environ["ENABLE_LLM_EXPLANATIONS"] = "false"
        assert intent_parser_from_env(KNOWN) is None
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # and with no parser at all the API answers deterministically
    body, _ = call(FRONT_VALID)
    assert body["interpreted_intent"]["source"] == "deterministic"


# --------------------------------------------------------------------------
# Explicit fields win
# --------------------------------------------------------------------------

def test_explicit_language_beats_inferred():
    body = {**FRONT_VALID, "language": "русский",
            "query": "Нужен фотограф, обязательно говорящий по-казахски"}
    got, _ = call(body, lambda q: intent(["Фотограф"], "казахский", required=True))
    info = got["interpreted_intent"]
    assert info["language"] == "казахский" and "language" not in info["applied"]
    assert "учтено: язык" not in got["message"]
    effective = {**_as_match_body(body), "services": ["фотограф"]}
    assert ids(got) == match_ids(effective)[:3]  # filtered by русский, not казахский
    for cid in ids(got):
        assert "русский" in next(c for c in CONTRACTORS if c.id == cid).languages


def test_inferred_required_language_applies_only_without_explicit():
    body = {**FRONT_VALID, "query": "фотограф, обязательно на казахском"}
    got, _ = call(body, lambda q: intent(["Фотограф"], "казахский", required=True))
    assert "language" in got["interpreted_intent"]["applied"]
    assert "учтено: язык — казахский" in got["message"]
    for cid in ids(got):
        assert "казахский" in next(c for c in CONTRACTORS if c.id == cid).languages
    effective = {**_as_match_body(body), "language": "казахский", "services": ["фотограф"]}
    assert ids(got) == match_ids(effective)[:3]
    # a mere preference never filters
    weak, _ = call(body, lambda q: intent(["Фотограф"], "казахский", required=False))
    assert "language" not in weak["interpreted_intent"]["applied"]
    assert ids(weak) == match_ids({**_as_match_body(body), "services": ["фотограф"]})[:3]


def test_explicit_category_beats_inferred_services():
    body = {**FRONT_VALID, "category": "Ведущий", "budget_kzt": 1_500_000,
            "query": "фотограф и видеограф"}
    got, _ = call(body, lambda q: intent(["Фотограф", "Видеограф"]))
    assert "services" not in got["interpreted_intent"]["applied"]
    assert got["service_intent"] is None
    assert all(c["category"] == "Ведущий" for c in got["cards"])
    assert ids(got) == match_ids(_as_match_body(body))[:3]


def test_explicit_event_type_beats_inferred_event():
    body = {**FRONT_VALID, "query": "фотограф на корпоратив"}
    got, _ = call(body, lambda q: intent(["Фотограф"], event_format="корпоратив"))
    assert got["interpreted_intent"]["event_format"] == "корпоратив"
    assert "event_format" not in got["interpreted_intent"]["applied"]
    for cid in ids(got):  # still filtered by the form's "свадьба"
        assert "свадьба" in next(c for c in CONTRACTORS if c.id == cid).event_formats


# --------------------------------------------------------------------------
# The LLM cannot touch selection / scores / order
# --------------------------------------------------------------------------

def test_llm_cannot_introduce_contractor_ids():
    baseline, _ = call(FRONT_VALID)
    got, _ = call(FRONT_VALID, lambda q: intent(
        ["Фотограф", "Видеограф", "HK-99999", "HK-68220"],
        best_contractor="HK-68220", contractor_ids=["HK-68220", "HK-99999"],
        ranking=["HK-68220"]))
    assert got["interpreted_intent"]["services"] == ["Видеограф", "Фотограф"]
    assert ids(got) == ids(baseline) == REFERENCE_IDS


def test_llm_cannot_change_scores():
    body = _as_match_body(FRONT_VALID)
    before = match_scores(body)
    for extra in ({"photographer_weight": 0.91, "videographer_weight": 0.73},
                  {"scores": {"HK-62242": 1.0}}):
        got, _ = call(FRONT_VALID, lambda q, e=extra: intent(["Фотограф", "Видеограф"], **e))
        assert ids(got) == REFERENCE_IDS
    # the effective request carries only labels -> identical scores on /match
    assert match_scores({**body, "services": ["фотограф", "видеограф"]}) == before


def test_llm_cannot_change_ordering():
    for services in (["Фотограф", "Видеограф"], ["Видеограф", "Фотограф"],
                     ["видеограф", "ФОТОГРАФ", "Фотограф"]):
        got, _ = call(FRONT_VALID, lambda q, s=services: intent(s))
        assert ids(got) == REFERENCE_IDS, services


def test_reference_request_unchanged():
    got, _ = call(FRONT_VALID, lambda q: intent(["Фотограф", "Видеограф"],
                                                event_format="свадьба"))
    assert ids(got) == REFERENCE_IDS
    assert got["interpreted_intent"] == {
        "services": ["Видеограф", "Фотограф"], "language": None, "language_required": False,
        "event_format": "свадьба", "source": "llm", "applied": ["services"]}
    off, _ = call(FRONT_VALID)
    assert ids(off) == REFERENCE_IDS
    assert {k: v for k, v in got.items() if k != "interpreted_intent"} == \
           {k: v for k, v in off.items() if k != "interpreted_intent"}


def test_llm_adds_understanding_deterministic_misses():
    body = {**FRONT_VALID, "query": "Нужен человек, который снимет всё на камеру"}
    plain, _ = call(body)
    assert plain["interpreted_intent"]["services"] == []   # keywords miss this
    got, _ = call(body, lambda q: intent(["Видеограф"]))
    assert got["service_intent"]["requested"] == ["Видеограф"]
    assert got["cards"][0]["category"] == "Видеограф"
    # still the matcher: same as /match with the validated label
    assert ids(got) == match_ids({**_as_match_body(body), "services": ["видеограф"]})[:3]


def test_intent_cached():
    parser, llm = parser_for(lambda q: intent(["Фотограф", "Видеограф"]))
    app.dependency_overrides[get_intent_parser] = lambda: parser
    try:
        a = client.post("/api/match", json=FRONT_VALID).json()
        b = client.post("/api/match", json=FRONT_VALID).json()
        c = client.post("/api/match", json={
            **FRONT_VALID, "query": "  нужен ФОТОГРАФ и видеограф   на свадьбу "}).json()
    finally:
        app.dependency_overrides[get_intent_parser] = lambda: None
    assert a == b and ids(c) == ids(a)
    assert len(llm.calls) == 1
    # failures are not cached: the next request asks again
    flaky = iter([RuntimeError("down"), intent(["Фотограф"])])
    parser, llm = parser_for(lambda q: next(flaky))
    assert parser.parse("фотограф") is None
    assert parser.parse("фотограф").services == ("Фотограф",)
    assert len(llm.calls) == 2


def test_prompt_lists_only_dataset_values():
    parser, llm = parser_for(lambda q: intent())
    parser.parse("что-нибудь")
    kwargs = llm.calls[0]
    system = kwargs["messages"][0]["content"]
    for cat in KNOWN.categories.values():
        assert cat in system
    assert "Never output contractor names or ids" in system
    assert kwargs["temperature"] == 0 and kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][1]["content"] == "что-нибудь"


def test_no_query_no_parser_call():
    body = {k: v for k, v in FRONT_VALID.items() if k != "query"}
    got, llm = call(body, lambda q: intent(["Фотограф"]))
    assert got["interpreted_intent"] is None and llm.calls == []


INTENT_TESTS = [
    ("Intent: simple service", test_simple_service),
    ("Intent: multiple services", test_multiple_services),
    ("Intent: language (required vs preferred)", test_language_extraction),
    ("Intent: event format", test_event_extraction),
    ("Intent: unknown values rejected", test_unknown_values_rejected),
    ("Intent: malformed answers rejected", test_malformed_answers_raise),
    ("Intent: invalid JSON -> deterministic", test_invalid_json_falls_back),
    ("Intent: timeout/errors -> deterministic", test_timeout_and_errors_fall_back),
    ("Intent: no API key -> deterministic", test_no_api_key_falls_back),
    ("Intent: explicit language wins", test_explicit_language_beats_inferred),
    ("Intent: required language applies, preference doesn't",
     test_inferred_required_language_applies_only_without_explicit),
    ("Intent: explicit category wins", test_explicit_category_beats_inferred_services),
    ("Intent: explicit event_type wins", test_explicit_event_type_beats_inferred_event),
    ("Intent: LLM cannot introduce ids", test_llm_cannot_introduce_contractor_ids),
    ("Intent: LLM cannot change scores", test_llm_cannot_change_scores),
    ("Intent: LLM cannot change ordering", test_llm_cannot_change_ordering),
    ("Intent: reference request unchanged", test_reference_request_unchanged),
    ("Intent: adds understanding keywords miss", test_llm_adds_understanding_deterministic_misses),
    ("Intent: cached", test_intent_cached),
    ("Intent: prompt uses dataset values only", test_prompt_lists_only_dataset_values),
    ("Intent: no query -> no call", test_no_query_no_parser_call),
]
