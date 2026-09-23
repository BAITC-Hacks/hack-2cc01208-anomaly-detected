from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data_loader import load_contractors
from .filters import MatchRequest
from .matcher import match

app = FastAPI(title="Contractor Matcher API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_df = load_contractors()


class MatchRequestBody(BaseModel):
    city: str
    date: str
    event_type: str
    category: str
    budget_kzt: int
    hours: float | None = None
    language: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "contractors_loaded": len(_df)}


@app.post("/api/match")
def post_match(body: MatchRequestBody):
    req = MatchRequest(**body.model_dump())
    return match(_df, req)


@app.get("/api/options")
def options():
    return {
        "cities": sorted(_df["city"].dropna().unique().tolist()),
        "categories": sorted(_df["categories"].explode().dropna().unique().tolist()),
        "event_formats": sorted(_df["event_formats"].explode().dropna().unique().tolist()),
        "languages": sorted(_df["languages"].explode().dropna().unique().tolist()),
    }
