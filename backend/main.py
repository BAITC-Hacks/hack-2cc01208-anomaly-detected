"""HTTP API over the deterministic matcher.

    uvicorn backend.main:app --reload

All matching logic lives in backend.matcher; this module only validates input,
calls match_with_rejections() and shapes the response.

    POST /match      detailed developer endpoint (scores, breakdowns, limit)
    POST /api/match  frontend contract from docs/api.md (backend/frontend_api.py)
"""

from __future__ import annotations

from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.data_loader import KnownValues, known_values, load_contractors
from backend.frontend_api import (
    MAX_CARDS,
    FrontendMatchRequest,
    FrontendMatchResponse,
    build_response,
    to_match_request,
    with_explanations,
    with_interpreted_intent,
)
from backend.intent_parser import (
    IntentParser,
    apply_intent,
    intent_parser_from_env,
    interpreted_intent,
)
from backend.llm_explainer import GroqExplainer, explainer_from_env
from backend.matcher import match_with_rejections
from backend.models import Contractor, MatchRequest, ScoreBreakdown

DEFAULT_LIMIT = 5
MAX_LIMIT = 20

# .env (git-ignored) -> GROQ_API_KEY, ENABLE_LLM_EXPLANATIONS, ENABLE_LLM_INTENT, ...
# Real environment variables win over .env.
load_dotenv()

# Loaded once at import; the dataset is read-only and small (66 rows).
CONTRACTORS: list[Contractor] = load_contractors()

# Every category/language/event format in the dataset (validates all LLM output).
KNOWN: KnownValues = known_values(CONTRACTORS)
KNOWN_CATEGORIES: dict[str, str] = KNOWN.categories  # normalized -> display

# None when the feature flag is off or no key: deterministic behaviour only.
EXPLAINER: GroqExplainer | None = explainer_from_env()
INTENT_PARSER: IntentParser | None = intent_parser_from_env(KNOWN)


def get_explainer() -> GroqExplainer | None:
    """FastAPI dependency, so tests can swap in a fake (no real Groq calls)."""
    return EXPLAINER


def get_intent_parser() -> IntentParser | None:
    """FastAPI dependency, so tests can swap in a fake (no real Groq calls)."""
    return INTENT_PARSER

app = FastAPI(
    title="Smart Contractor Matching",
    version="0.2.0",
    description="Deterministic contractor matching over the organizers' dataset.",
)

# The frontend is plain static files (may be opened as file://), see docs/api.md.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-Explanations"],
)


class ContractorOut(BaseModel):
    id: str
    name: str
    categories: list[str]
    city: str
    price_from_kzt: int
    event_formats: list[str]
    languages: list[str]
    max_hours: float | None
    synthetic: bool
    price_imputed: bool
    city_imputed: bool
    description: str

    @classmethod
    def from_contractor(cls, c: Contractor) -> "ContractorOut":
        return cls(
            id=c.id,
            name=c.anon_name,
            categories=list(c.categories_display),
            city=c.city,
            price_from_kzt=c.price_from_kzt,
            event_formats=list(c.event_formats),
            languages=list(c.languages),
            max_hours=c.max_hours,
            synthetic=c.synthetic,
            price_imputed=c.price_imputed,
            city_imputed=c.city_imputed,
            description=c.description,
        )


class MatchResult(BaseModel):
    contractor: ContractorOut
    score: float
    score_breakdown: ScoreBreakdown


class MatchResponse(BaseModel):
    request: MatchRequest
    eligible_count: int
    excluded: dict[str, int]  # hard rule -> contractors it removed
    results: list[MatchResult]


class HealthResponse(BaseModel):
    status: str
    contractors_loaded: int


class OptionsResponse(BaseModel):
    cities: list[str]
    categories: list[str]
    event_formats: list[str]
    languages: list[str]


# Computed once at import from the same CONTRACTORS/KNOWN the matcher uses, so
# the dropdowns can never drift out of sync with what /api/match actually accepts.
CITIES: list[str] = sorted({c.city for c in CONTRACTORS})
OPTIONS = OptionsResponse(
    cities=CITIES,
    categories=sorted(KNOWN_CATEGORIES.values()),
    event_formats=sorted(KNOWN.event_formats.values()),
    languages=sorted(KNOWN.languages.values()),
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", contractors_loaded=len(CONTRACTORS))


@app.get("/api/options", response_model=OptionsResponse)
def options() -> OptionsResponse:
    """docs/api.md: optional; the frontend falls back to a hardcoded list if this is absent."""
    return OPTIONS


@app.post("/match", response_model=MatchResponse)
def match_endpoint(
    req: MatchRequest,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> MatchResponse:
    ranked, rejected = match_with_rejections(CONTRACTORS, req)
    return MatchResponse(
        request=req,
        eligible_count=len(ranked),
        excluded=dict(sorted(rejected.items())),
        results=[
            MatchResult(
                contractor=ContractorOut.from_contractor(s.contractor),
                score=s.score.total,
                score_breakdown=s.score,
            )
            for s in ranked[:limit]
        ],
    )


@app.post("/api/match", response_model=FrontendMatchResponse)
def frontend_match_endpoint(
    req: FrontendMatchRequest,
    response: Response,
    explainer: Annotated[GroqExplainer | None, Depends(get_explainer)],
    intent_parser: Annotated[IntentParser | None, Depends(get_intent_parser)],
) -> FrontendMatchResponse:
    """Frontend contract (docs/api.md): up to 3 cards, same engine and order as /match.

    Optional LLM steps never choose or order contractors:
      1. intent parser: query -> validated labels -> effective MatchRequest
         (explicit form fields win); `interpreted_intent` shows the result.
         POST /match with that effective request returns the same order.
      2. explainer: rewrites card explanations (looked up by id).
    Header X-Explanations says which texts were used: template | llm | mixed.
    """
    match_req = to_match_request(req)
    parsed = intent_parser.parse(match_req.query) if intent_parser and match_req.query else None
    effective, applied = apply_intent(match_req, parsed, KNOWN)

    ranked, rejected = match_with_rejections(CONTRACTORS, effective)
    result = build_response(ranked, rejected, effective, KNOWN_CATEGORIES)
    result = with_interpreted_intent(
        result, interpreted_intent(match_req, parsed, applied, KNOWN))

    source = "template"
    if explainer is not None and result.cards:
        provides = (
            {card.id: not card.alternative for card in result.cards}
            if result.service_intent is not None else None
        )
        texts = explainer.explain_matches(effective, ranked[:MAX_CARDS], provides)
        if texts:
            result = with_explanations(result, texts)
            source = "llm" if all(c.id in texts for c in result.cards) else "mixed"
    response.headers["X-Explanations"] = source
    return result
