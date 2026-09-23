import pandas as pd

from app.data_loader import load_contractors
from app.filters import EXCLUSION_REASONS, MatchRequest, filter_contractors

df = load_contractors()


def test_found_status_for_dense_category():
    req = MatchRequest(city="Алматы", date="2026-10-15", event_type="корпоратив",
                        category="Фотограф", budget_kzt=2_000_000)
    r = filter_contractors(df, req)
    assert r.status == "found"
    assert len(r.survivors) > 0


def test_no_category_status():
    # There is no "Отель" category recorded for every city in the catalog —
    # find one real (city, category) combination guaranteed absent.
    present = {(row.city, cat) for row in df.itertuples() for cat in row.categories}
    all_cities = df["city"].unique()
    all_categories = df["categories"].explode().dropna().unique()
    missing = next(
        (c, cat) for c in all_cities for cat in all_categories if (c, cat) not in present
    )
    req = MatchRequest(city=missing[0], date="2026-10-15", event_type="корпоратив",
                        category=missing[1], budget_kzt=10_000_000)
    r = filter_contractors(df, req)
    assert r.status == "no_category"


def test_none_fit_status_reports_reasons():
    req = MatchRequest(city="Астана", date="2026-10-15", event_type="свадьба",
                        category="Отель", budget_kzt=1)  # budget impossibly low
    r = filter_contractors(df, req)
    assert r.status == "none_fit"
    assert len(r.rejected) > 0
    assert all(candidate.reasons for candidate in r.rejected)


def test_excluded_breakdown_always_present_and_accurate():
    req = MatchRequest(city="Астана", date="2026-10-15", event_type="свадьба",
                        category="Отель", budget_kzt=1)
    r = filter_contractors(df, req)
    assert set(r.excluded.keys()) == set(EXCLUSION_REASONS)
    assert r.excluded["over_budget"] == r.category_pool_size  # budget=1 fails everyone on price

    # excluded is present for `found` too, not just none_fit/no_category
    req_found = MatchRequest(city="Алматы", date="2026-10-15", event_type="корпоратив",
                              category="Фотограф", budget_kzt=2_000_000)
    r_found = filter_contractors(df, req_found)
    assert r_found.status == "found"
    assert set(r_found.excluded.keys()) == set(EXCLUSION_REASONS)


def test_busy_date_actually_excludes():
    req = MatchRequest(city="Алматы", date="2026-10-15", event_type="корпоратив",
                        category="Фотограф", budget_kzt=10_000_000)
    r = filter_contractors(df, req)
    for _, row in r.survivors.iterrows():
        assert "2026-10-15" not in row["busy_dates"]


def test_language_filter_excludes_non_matching():
    req = MatchRequest(city="Алматы", date="2026-10-15", event_type="корпоратив",
                        category="Ведущий", budget_kzt=10_000_000, language="английский")
    r = filter_contractors(df, req)
    assert r.status == "found"
    assert len(r.survivors) > 0
    for _, row in r.survivors.iterrows():
        assert "английский" in row["languages"]
    # sanity: without the language filter this category/city has hosts who DON'T speak English
    unfiltered = filter_contractors(df, MatchRequest(
        city="Алматы", date="2026-10-15", event_type="корпоратив", category="Ведущий", budget_kzt=10_000_000,
    ))
    assert len(unfiltered.survivors) > len(r.survivors)


def test_duration_filter_excludes_shorter_max_hours():
    req = MatchRequest(city="Алматы", date="2026-10-15", event_type="корпоратив",
                        category="Ведущий", budget_kzt=10_000_000, hours=9)
    r = filter_contractors(df, req)
    assert r.status == "found"
    for _, row in r.survivors.iterrows():
        assert pd.isna(row["max_hours"]) or row["max_hours"] >= 9


def test_duration_filter_never_excludes_venue_independent_contractors():
    # max_hours == NaN means the work isn't tied to on-site presence
    # (florist, decorator, souvenirs) — an arbitrarily large duration must
    # not exclude them.
    req = MatchRequest(city="Алматы", date="2026-10-20", event_type="свадьба",
                        category="Флорист", budget_kzt=10_000_000, hours=48)
    r = filter_contractors(df, req)
    assert r.status == "found"
    assert len(r.survivors) > 0


def test_venue_category_uses_the_same_generic_pipeline():
    # The brief calls this out explicitly: "find a hall for Nov 14" is the
    # same kind of request as any other category, just category=Банкетный зал.
    req = MatchRequest(city="Алматы", date="2026-11-14", event_type="свадьба",
                        category="Банкетный зал", budget_kzt=5_000_000)
    r = filter_contractors(df, req)
    assert r.status in {"found", "none_fit"}  # exercised the real pipeline, not a special case
    assert r.category_pool_size > 0
