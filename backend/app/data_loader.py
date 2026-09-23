"""Loads the 66-profile contractor dataset from hackathon-dataset-anonymized.jsonl
(one JSON object per line — categories/event_formats/languages/busy_dates
are already real arrays in this format, no delimiter parsing needed).

The brief explicitly invites adding your own synthetic profiles (marked
synthetic: true) if a demo query needs coverage the real 66 records don't
have — `load_contractors` accepts an `extra_synthetic` list for that,
kept empty by default so real vs. synthetic stays an explicit choice, not
something silently injected.
"""
from __future__ import annotations

import json

import pandas as pd

from . import config


def _read_jsonl(path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_contractors(extra_synthetic: list[dict] | None = None) -> pd.DataFrame:
    records = _read_jsonl(config.DATA_PATH)
    if extra_synthetic:
        for rec in extra_synthetic:
            rec = dict(rec)
            rec["synthetic"] = True
            records.append(rec)

    df = pd.DataFrame(records)

    for col in ["categories", "event_formats", "languages", "busy_dates"]:
        df[col] = df[col].apply(lambda v: v if isinstance(v, list) else [])

    df["price_from_kzt"] = pd.to_numeric(df["price_from_kzt"], errors="coerce")
    df["max_hours"] = pd.to_numeric(df["max_hours"], errors="coerce")  # null/NaN = not tied to on-site presence

    for flag in ["synthetic", "city_imputed", "price_imputed"]:
        if flag in df.columns:
            df[flag] = df[flag].fillna(False).astype(bool)

    return df.reset_index(drop=True)
