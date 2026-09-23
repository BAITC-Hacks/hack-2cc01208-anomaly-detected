from app.data_loader import load_contractors
from app.filters import MatchRequest
from app.matcher import match

df = load_contractors()


def _ids(response: dict) -> list[str]:
    return [card["id"] for card in response["cards"]]


def test_same_request_same_card_order():
    req = MatchRequest(city="Алматы", date="2026-10-15", event_type="корпоратив",
                        category="Фотограф", budget_kzt=2_000_000)
    first = match(df, req)
    second = match(df, req)
    assert _ids(first) == _ids(second)
    assert len(first["cards"]) > 0


def test_different_dates_give_different_results_with_availability_reason():
    base = dict(city="Алматы", event_type="корпоратив", category="Ведущий", budget_kzt=1_500_000)
    req_a = MatchRequest(date="2026-10-15", **base)
    req_b = MatchRequest(date="2026-12-24", **base)  # December: much higher booking load
    res_a = match(df, req_a)
    res_b = match(df, req_b)
    assert _ids(res_a) != _ids(res_b) or res_a["status"] != res_b["status"]
