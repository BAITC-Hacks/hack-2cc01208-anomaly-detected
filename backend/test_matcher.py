"""Tests + demo for the deterministic matcher, run against the real dataset.

    python -m backend.test_matcher

Also collectable by pytest (every check is a plain `test_*` function).
"""

from __future__ import annotations

import hashlib
import os
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from pydantic import ValidationError

from backend.data_loader import DEFAULT_DATASET, EXPECTED_COLUMNS, load_contractors
from backend.matcher import (
    MODE_RELEVANCE,
    MODE_STRUCTURED,
    REJECT_BUDGET,
    REJECT_BUSY,
    REJECT_CATEGORY,
    REJECT_CITY,
    REJECT_DURATION,
    REJECT_FORMAT,
    REJECT_LANGUAGE,
    hard_filter,
    match,
    match_with_rejections,
)
from backend.models import Contractor, MatchRequest, normalize_text
from backend.relevance import analyze_request, relevance, stem, tokenize

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
EXPECTED_RECORDS = 66

CONTRACTORS = load_contractors()

# Value sets taken from the data itself, so the sweeps cover every real option.
CITIES = sorted({c.city for c in CONTRACTORS})
FORMATS = sorted({f for c in CONTRACTORS for f in c.event_formats})
LANGUAGES = sorted({lang for c in CONTRACTORS for lang in c.languages})
CATEGORIES = sorted({cat for c in CONTRACTORS for cat in c.categories})
ALL_BUSY = sorted({d for c in CONTRACTORS for d in c.busy_dates})
FIRST_DAY, LAST_DAY = date.fromisoformat(ALL_BUSY[0]), date.fromisoformat(ALL_BUSY[-1])
ALL_DATES = [
    (FIRST_DAY + timedelta(days=i)).isoformat()
    for i in range((LAST_DAY - FIRST_DAY).days + 2)  # +1 day past the last busy date
]
BUDGETS = [None, 150_000, 300_000, 500_000, 1_000_000]


def _by_id(cid: str):
    return next(c for c in CONTRACTORS if c.id == cid)


def _ids(results) -> list[str]:
    return [s.contractor.id for s in results]


def _sweep(extra: dict | None = None):
    """Yield (request, results) for city x format x date x budget (+ extra fields)."""
    for city in CITIES:
        for fmt in FORMATS:
            for d in ALL_DATES:
                for budget in BUDGETS:
                    req = MatchRequest(
                        city=city, event_format=fmt, event_date=d,
                        budget_kzt=budget, **(extra or {}),
                    )
                    yield req, match(CONTRACTORS, req)


# --------------------------------------------------------------------------
# 1-2. Loading
# --------------------------------------------------------------------------

def test_csv_loads():
    assert CONTRACTORS, "no contractors loaded"
    for c in CONTRACTORS:
        assert c.id and c.anon_name and c.city_norm
        assert c.categories and c.event_formats and c.languages
        assert c.price_from_kzt > 0
        assert all(f == normalize_text(f) for f in c.event_formats)
    # '|'-separated fields became real lists
    choppper = _by_id("HK-39372")
    assert choppper.event_formats == ("свадьба", "корпоратив", "конференция", "юбилей")
    assert "2026-09-25" in choppper.busy_dates
    # Missing max_hours stays None instead of being invented
    assert any(c.max_hours is None for c in CONTRACTORS)


def test_record_count():
    assert len(CONTRACTORS) == EXPECTED_RECORDS, len(CONTRACTORS)
    assert len({c.id for c in CONTRACTORS}) == EXPECTED_RECORDS


def test_columns_match_spec():
    import csv
    with DEFAULT_DATASET.open(encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
    assert tuple(header) == EXPECTED_COLUMNS, header


# --------------------------------------------------------------------------
# 3-7. Hard filters (targeted cases + exhaustive sweeps)
# --------------------------------------------------------------------------

def test_busy_date_targeted():
    c = _by_id("HK-39372")  # Алматы, свадьба, busy on 2026-09-25
    busy_req = MatchRequest(city="Алматы", event_format="свадьба", event_date="2026-09-25")
    free_req = MatchRequest(city="Алматы", event_format="свадьба", event_date="2026-09-26")
    assert "2026-09-26" not in c.busy_dates
    assert c.id not in _ids(match(CONTRACTORS, busy_req))
    assert c.id in _ids(match(CONTRACTORS, free_req))  # proves the filter isn't over-eager


def test_busy_date_never_returned():
    rejected = 0
    for req, results in _sweep():
        for s in results:
            assert req.event_date not in s.contractor.busy_dates, (req, s.contractor.id)
        rejected += hard_filter(CONTRACTORS, req)[1].get(REJECT_BUSY, 0)
    assert rejected > 0, "busy filter never triggered — sweep is vacuous"


def test_city_filter():
    rejected = 0
    for req, results in _sweep():
        for s in results:
            assert s.contractor.city_norm == normalize_text(req.city)
        rejected += hard_filter(CONTRACTORS, req)[1].get(REJECT_CITY, 0)
    assert rejected > 0
    # Case/whitespace-insensitive, but no invented aliases
    a = MatchRequest(city="  алматы ", event_format="Свадьба", event_date="2026-10-10")
    b = MatchRequest(city="Алматы", event_format="свадьба", event_date="2026-10-10")
    assert _ids(match(CONTRACTORS, a)) == _ids(match(CONTRACTORS, b))
    assert match(CONTRACTORS, MatchRequest(city="Шымкент", event_format="свадьба",
                                           event_date="2026-10-10")) == []


def test_budget_filter():
    rejected = 0
    for req, results in _sweep():
        for s in results:
            if req.budget_kzt is not None:
                assert s.contractor.price_from_kzt <= req.budget_kzt
                assert 0.0 <= s.score.budget <= 1.0
        rejected += hard_filter(CONTRACTORS, req)[1].get(REJECT_BUDGET, 0)
    assert rejected > 0


def test_event_format_filter():
    rejected = 0
    for req, results in _sweep():
        for s in results:
            assert normalize_text(req.event_format) in s.contractor.event_formats
        rejected += hard_filter(CONTRACTORS, req)[1].get(REJECT_FORMAT, 0)
    assert rejected > 0
    assert match(CONTRACTORS, MatchRequest(city="Алматы", event_format="выпускной",
                                           event_date="2026-10-10")) == []


def test_language_filter():
    rejected = 0
    for lang in LANGUAGES:
        for req, results in _sweep({"language": lang}):
            for s in results:
                assert normalize_text(lang) in s.contractor.languages
            rejected += hard_filter(CONTRACTORS, req)[1].get(REJECT_LANGUAGE, 0)
    assert rejected > 0


def test_category_filter_exact_item():
    rejected = 0
    for cat in CATEGORIES:
        req = MatchRequest(city="Алматы", event_format="свадьба",
                           event_date="2026-10-10", category=cat)
        for s in match(CONTRACTORS, req):
            assert cat in s.contractor.categories
        rejected += hard_filter(CONTRACTORS, req)[1].get(REJECT_CATEGORY, 0)
    assert rejected > 0
    # "Ведущий" must not substring-match "Ведущий церемонии"
    hosts = MatchRequest(city="Алматы", event_format="свадьба",
                         event_date="2026-10-10", category="Ведущий")
    for s in match(CONTRACTORS, hosts):
        assert "ведущий" in s.contractor.categories


def test_duration_filter():
    rejected = 0
    for hours in (1, 5, 9, 11, 13):
        req = MatchRequest(city="Алматы", event_format="свадьба",
                           event_date="2026-10-10", duration_hours=hours)
        for s in match(CONTRACTORS, req):
            mh = s.contractor.max_hours
            assert mh is None or hours <= mh
        rejected += hard_filter(CONTRACTORS, req)[1].get(REJECT_DURATION, 0)
    assert rejected > 0


def test_request_validation():
    for bad in ("10.10.2026", "2026-02-30", "20261010", "2026-W41-6", ""):
        try:
            MatchRequest(city="Алматы", event_format="свадьба", event_date=bad)
        except ValidationError:
            continue
        raise AssertionError(f"accepted bad date {bad!r}")
    for field, value in (("budget_kzt", 0), ("duration_hours", -1), ("city", "  ")):
        kwargs = {"city": "Алматы", "event_format": "свадьба", "event_date": "2026-10-10"}
        kwargs[field] = value
        try:
            MatchRequest(**kwargs)
        except ValidationError:
            continue
        raise AssertionError(f"accepted bad {field}={value!r}")


# --------------------------------------------------------------------------
# 8-9. Determinism
# --------------------------------------------------------------------------

DEMO_REQUEST = MatchRequest(
    city="Алматы", event_format="свадьба", event_date="2026-10-10", budget_kzt=500_000,
)


def test_deterministic_ordering():
    first = match(CONTRACTORS, DEMO_REQUEST)
    second = match(CONTRACTORS, DEMO_REQUEST)
    assert first and _ids(first) == _ids(second)
    assert [s.score for s in first] == [s.score for s in second]

    # Input order must not matter (seeded shuffle only — used by the TEST, not the matcher).
    shuffled = list(CONTRACTORS)
    random.Random(42).shuffle(shuffled)
    assert _ids(match(shuffled, DEMO_REQUEST)) == _ids(first)
    assert _ids(match(list(reversed(CONTRACTORS)), DEMO_REQUEST)) == _ids(first)

    # Sorted by score desc, id asc on ties
    keys = [(-s.score.total, s.contractor.id) for s in first]
    assert keys == sorted(keys)


def test_no_randomness():
    # 1) Matcher code imports nothing nondeterministic.
    forbidden = ("import random", "from random", "import secrets", "uuid",
                 "datetime.now", "time.time", "date.today")
    for name in ("models.py", "data_loader.py", "relevance.py", "matcher.py", "main.py",
                 "frontend_api.py", "llm_explainer.py", "intent_parser.py"):
        src = (BACKEND_DIR / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in src, f"{name} contains {token!r}"

    # 2) Fresh interpreters with different hash seeds give identical output.
    snippet = (
        "from backend.data_loader import load_contractors;"
        "from backend.matcher import match;"
        "from backend.models import MatchRequest;"
        "cs=load_contractors();"
        "reqs=[MatchRequest(city='Алматы',event_format='свадьба',event_date='2026-10-10',budget_kzt=500000),"
        "MatchRequest(city='Алматы',event_format='свадьба',event_date='2026-10-10',"
        "query='Нужен фотограф и видеограф, живая музыка и цветы'),"
        "MatchRequest(city='Астана',event_format='корпоратив',event_date='2026-11-01',language='английский')];"
        "print([[(s.contractor.id,s.score.total) for s in match(cs,r)] for r in reqs])"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run(
            [sys.executable, "-c", snippet], cwd=REPO_ROOT, env=env,
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
        outputs.add(out)
    assert len(outputs) == 1, "ordering changed between interpreter runs"


def test_csv_not_modified():
    before = hashlib.sha256(DEFAULT_DATASET.read_bytes()).hexdigest()
    load_contractors()
    for _ in _sweep():
        pass
    after = hashlib.sha256(DEFAULT_DATASET.read_bytes()).hexdigest()
    assert before == after


# --------------------------------------------------------------------------
# Relevance + ranking — controlled fixtures (prove the LOGIC, not the CSV)
# --------------------------------------------------------------------------

FIXTURE_DATE = "2026-10-10"


def make_contractor(
    cid: str,
    categories: tuple[str, ...],
    price: int,
    *,
    description: str = "Работаем на мероприятиях в Алматы.",
    synthetic: bool = False,
    price_imputed: bool = False,
    city_imputed: bool = False,
    languages: tuple[str, ...] = ("русский",),
) -> Contractor:
    """A contractor that passes the hard filters of fixture_request()."""
    return Contractor(
        id=cid, anon_name=f"Fixture {cid}",
        categories=tuple(normalize_text(c) for c in categories),
        categories_display=categories,
        city="Алматы", city_norm="алматы", city_imputed=city_imputed,
        synthetic=synthetic, price_from_kzt=price, price_imputed=price_imputed,
        event_formats=("свадьба",), languages=languages, max_hours=None,
        busy_dates=frozenset(), description=description,
    )


def fixture_request(**kw) -> MatchRequest:
    base = {"city": "Алматы", "event_format": "свадьба", "event_date": FIXTURE_DATE,
            "budget_kzt": 500_000}
    return MatchRequest(**{**base, **kw})


def _order(results) -> list[str]:
    return [s.contractor.id for s in results]


def test_text_normalization():
    assert tokenize("Нужен ФОТОГРАФ, и видеограф!!  на свадьбу...") == (
        "фотограф", "видеограф", "свадьбу")
    assert tokenize("Ёлка — ёжик") == ("елка", "ежик")
    assert tokenize("Қазақша тойға әнші керек") == ("қазақша", "тойға", "әнші")
    assert tokenize(None) == () and tokenize("   ") == ()
    assert stem("фотографа") == stem("фотографы") == "фотограф"
    assert stem("ведущего") == stem("ведущий") == "ведущ"
    # Hard-filtered words (event format, city) are not part of the "need".
    intent = analyze_request(fixture_request(query="Фотограф на свадьбу в Алматы"))
    assert intent.stems == ("фотограф",)


def test_query_changes_ranking():
    florist = make_contractor("FX-001", ("Флорист",), 100_000)
    photo = make_contractor("FX-002", ("Фотограф",), 400_000)
    no_query = match([florist, photo], fixture_request())
    with_query = match([florist, photo], fixture_request(query="Нужен фотограф на свадьбу"))
    assert _order(no_query) == ["FX-001", "FX-002"]  # nothing to be relevant to: cheaper first
    assert no_query[0].score.mode == MODE_STRUCTURED
    assert _order(with_query) == ["FX-002", "FX-001"]
    assert with_query[0].score.mode == MODE_RELEVANCE
    assert with_query[0].score.relevance > with_query[1].score.relevance


def test_category_beats_cheaper_unrelated():
    # Worst case for the relevant one: 3 categories, priced AT the budget, every
    # data-quality flag bad. Best case for the unrelated one: nearly free, clean data.
    relevant = make_contractor(
        "FX-900", ("Фотограф", "Декоратор", "Отель"), 500_000,
        synthetic=True, price_imputed=True, city_imputed=True)
    unrelated = make_contractor("FX-001", ("Флорист",), 1)
    ranked = match([unrelated, relevant], fixture_request(query="Нужен фотограф"))
    assert _order(ranked) == ["FX-900", "FX-001"], [(s.contractor.id, s.score) for s in ranked]


def test_category_beats_description_mention():
    photographer = make_contractor("FX-002", ("Фотограф",), 300_000)
    florist = make_contractor(
        "FX-001", ("Флорист",), 300_000,
        description="Флористика. Дружим с лучшими фотографами города, фотограф в подарок.")
    ranked = match([florist, photographer], fixture_request(query="фотограф"))
    assert _order(ranked) == ["FX-002", "FX-001"]
    assert ranked[1].score.description_overlap > 0   # the mention is noticed...
    assert ranked[1].score.category_match == 0       # ...but isn't a category
    assert ranked[0].score.relevance > ranked[1].score.relevance


def test_specialist_preferred():
    specialist = make_contractor("FX-002", ("Фотограф",), 300_000)
    generalist = make_contractor("FX-001", ("Фотограф", "Видеограф", "Флорист"), 300_000)
    ranked = match([generalist, specialist], fixture_request(query="фотограф"))
    assert _order(ranked) == ["FX-002", "FX-001"]
    assert ranked[0].score.specialization == 1.0
    assert abs(ranked[1].score.specialization - 1 / 3) < 1e-6
    # Covering two of the asked services counts for more than one.
    both = match([generalist], fixture_request(query="фотограф и видеограф"))[0]
    assert abs(both.score.specialization - 2 / 3) < 1e-6


def test_keywords_and_word_forms():
    band = make_contractor("FX-001", ("Лайв-бэнд",), 300_000)
    host = make_contractor("FX-002", ("Ведущий",), 300_000)
    flor = make_contractor("FX-003", ("Флорист",), 300_000)
    cases = {
        "нужна кавер группа": "FX-001",
        "ищем ведущего на вечер": "FX-002",
        "тамада": "FX-002",
        "букеты и цветы": "FX-003",
    }
    for query, expected in cases.items():
        ranked = match([band, host, flor], fixture_request(query=query))
        assert ranked[0].contractor.id == expected, (query, _order(ranked))
        assert ranked[0].score.category_match == 1.0
        assert all(s.score.category_match == 0.0 for s in ranked[1:]), query


def test_language_not_scored():
    a = make_contractor("FX-001", ("Фотограф",), 300_000, languages=("русский", "казахский"))
    b = make_contractor("FX-002", ("Фотограф",), 300_000, languages=("казахский",))
    without = {s.contractor.id: s.score.total for s in match([a, b], fixture_request(query="фото"))}
    with_lang = {s.contractor.id: s.score.total
                 for s in match([a, b], fixture_request(query="фото", language="казахский"))}
    assert without == with_lang  # language filters, never boosts


def test_real_data_photo_query_relevance():
    """Property on the real CSV — no specific contractor is required to be #1."""
    req = MatchRequest(city="Алматы", event_format="свадьба", event_date=FIXTURE_DATE,
                       query="Нужен фотограф и видеограф на свадьбу")
    ranked = match(CONTRACTORS, req)
    media = [s for s in ranked if {"фотограф", "видеограф"} & set(s.contractor.categories)]
    other = [s for s in ranked if s not in media]
    assert media and other
    assert all(s.score.category_match == 1.0 for s in media)
    assert min(s.score.relevance for s in media) > max(s.score.relevance for s in other)
    assert min(s.score.total for s in media) > max(s.score.total for s in other)


def test_scores_bounded_and_explained():
    for city in CITIES:
        for fmt in FORMATS:
            for query in (None, "фотограф видео ведущий цветы", "!!!", "фотограф свадьба"):
                req = MatchRequest(city=city, event_format=fmt, event_date=FIXTURE_DATE,
                                   budget_kzt=1_000_000, query=query)
                for s in match(CONTRACTORS, req):
                    sc = s.score
                    for v in (sc.relevance, sc.category_match, sc.description_overlap,
                              sc.budget, sc.confidence, sc.specialization, sc.total):
                        assert 0.0 <= v <= 1.0, sc
                    assert bool(sc.matched_categories) == (sc.category_match == 1.0)
                    if sc.mode == MODE_STRUCTURED:
                        assert sc.relevance == 0 and sc.specialization == 0


# --------------------------------------------------------------------------
# Runner + demo
# --------------------------------------------------------------------------

TESTS = [
    ("CSV loading", test_csv_loads),
    ("Record count (66)", test_record_count),
    ("Column header", test_columns_match_spec),
    ("Busy date filtering (targeted)", test_busy_date_targeted),
    ("Busy date filtering (full sweep)", test_busy_date_never_returned),
    ("City filtering", test_city_filter),
    ("Budget filtering", test_budget_filter),
    ("Event format filtering", test_event_format_filter),
    ("Language filtering", test_language_filter),
    ("Category filtering", test_category_filter_exact_item),
    ("Duration filtering", test_duration_filter),
    ("Request validation", test_request_validation),
    ("Deterministic ordering", test_deterministic_ordering),
    ("No randomness", test_no_randomness),
    ("CSV unchanged", test_csv_not_modified),
    # relevance / ranking (controlled fixtures unless noted)
    ("Text normalization", test_text_normalization),
    ("Query changes ranking", test_query_changes_ranking),
    ("Category beats cheaper unrelated", test_category_beats_cheaper_unrelated),
    ("Category beats description mention", test_category_beats_description_mention),
    ("Specialist preferred", test_specialist_preferred),
    ("Keywords and word forms", test_keywords_and_word_forms),
    ("Language not scored", test_language_not_scored),
    ("Real data: photo/video query", test_real_data_photo_query_relevance),
    ("Scores bounded and explained", test_scores_bounded_and_explained),
]


def _fmt_kzt(n: int | None) -> str:
    return "—" if n is None else f"{n:,} KZT".replace(",", " ")


def print_demo(req: MatchRequest, top: int = 5) -> None:
    results, rejected = match_with_rejections(CONTRACTORS, req)

    print("REQUEST")
    print(f"City: {req.city}")
    print(f"Event: {req.event_format}")
    print(f"Date: {req.event_date}")
    print(f"Budget: {_fmt_kzt(req.budget_kzt)}")
    for label, value in (("Category", req.category), ("Language", req.language),
                         ("Duration", req.duration_hours), ("Query", req.query)):
        if value:
            print(f"{label}: {value}")
    print()
    print(f"REJECTED: {sum(rejected.values())}  "
          + ", ".join(f"{k}={v}" for k, v in sorted(rejected.items())))
    print(f"ELIGIBLE CONTRACTORS: {len(results)}"
          + (f"  (showing top {top})" if len(results) > top else ""))
    print()
    for i, s in enumerate(results[:top], 1):
        c, sc = s.contractor, s.score
        flags = [name for name, on in (("synthetic", c.synthetic),
                                       ("price imputed", c.price_imputed),
                                       ("city imputed", c.city_imputed)) if on]
        print(f"{i}. {c.anon_name}")
        print(f"   ID: {c.id}")
        print(f"   Category: {', '.join(c.categories_display)}")
        print(f"   Price: from {_fmt_kzt(c.price_from_kzt)}")
        print(f"   Languages: {', '.join(c.languages)}")
        print(f"   Score: {sc.total:.4f}  [{sc.mode}] relevance {sc.relevance:.3f}, "
              f"budget {sc.budget:.3f}, confidence {sc.confidence:.2f}, "
              f"specialization {sc.specialization:.2f}")
        if sc.matched_categories or sc.matched_terms:
            print(f"   Matched: categories={list(sc.matched_categories)} "
                  f"description terms={list(sc.matched_terms)}")
        if flags:
            print(f"   Data flags: {', '.join(flags)}")
        print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # imported here so pytest doesn't collect them twice
    from backend.test_api import API_TESTS
    from backend.test_frontend_api import FRONTEND_TESTS
    from backend.test_llm_explainer import LLM_TESTS
    from backend.test_service_intent import SERVICE_TESTS
    from backend.test_intent_parser import INTENT_TESTS

    print(f"Loaded contractors: {len(CONTRACTORS)}")
    print()
    failed = 0
    sections = (("MATCHER", TESTS), ("API /match", API_TESTS),
                ("API /api/match", FRONTEND_TESTS), ("LLM explanations (fake Groq)", LLM_TESTS),
                ("Service intent", SERVICE_TESTS), ("AI intent parser (fake Groq)", INTENT_TESTS))
    for section, tests in sections:
        print(f"--- {section} ({len(tests)}) ---")
        for name, fn in tests:
            try:
                fn()
                print(f"{name}: PASSED")
            except Exception as exc:  # noqa: BLE001 — report every failure, keep going
                failed += 1
                print(f"{name}: FAILED  -> {type(exc).__name__}: {exc}")
        print()
    total = sum(len(tests) for _, tests in sections)
    print(f"ALL {total} TESTS PASSED" if not failed else f"{failed}/{total} TEST(S) FAILED")
    print()
    print("=" * 60)
    print_demo(DEMO_REQUEST.model_copy(update={"query": "Нужен фотограф и видеограф на свадьбу"}))
    print("=" * 60)
    print_demo(DEMO_REQUEST)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
