"""Load the organizers' contractor CSV into immutable Contractor models.

The CSV is opened read-only and never modified.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from backend.models import Contractor, normalize_text

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "data" / "hackathon_dataset.csv"

EXPECTED_COLUMNS = (
    "id", "anon_name", "categories", "city", "city_imputed", "synthetic",
    "price_from_kzt", "price_imputed", "event_formats", "languages",
    "max_hours", "busy_dates", "description",
)

LIST_SEPARATOR = "|"


def split_list(raw: str | None, *, normalize: bool = True) -> tuple[str, ...]:
    """'a|b| c' -> ('a', 'b', 'c'). Empty/missing -> (). Order kept, duplicates dropped."""
    items: list[str] = []
    for part in (raw or "").split(LIST_SEPARATOR):
        value = normalize_text(part) if normalize else " ".join(part.split())
        if value and value not in items:
            items.append(value)
    return tuple(items)


def parse_bool(raw: str | None, *, field: str, row_id: str) -> bool:
    value = normalize_text(raw)
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    raise ValueError(f"{row_id}: cannot parse boolean {field}={raw!r}")


def parse_optional_float(raw: str | None) -> float | None:
    value = normalize_text(raw)
    if value in ("", "nan", "none", "null"):
        return None
    return float(value)


def parse_busy_dates(raw: str | None, *, row_id: str) -> frozenset[str]:
    dates = set()
    for item in split_list(raw):
        try:
            dates.add(date.fromisoformat(item).isoformat())
        except ValueError as exc:
            raise ValueError(f"{row_id}: bad busy date {item!r}") from exc
    return frozenset(dates)


def parse_row(row: dict[str, str]) -> Contractor:
    row_id = (row.get("id") or "").strip()
    if not row_id:
        raise ValueError(f"row without id: {row!r}")
    return Contractor(
        id=row_id,
        anon_name=(row.get("anon_name") or "").strip(),
        categories=split_list(row.get("categories")),
        categories_display=split_list(row.get("categories"), normalize=False),
        city=(row.get("city") or "").strip(),
        city_norm=normalize_text(row.get("city")),
        city_imputed=parse_bool(row.get("city_imputed"), field="city_imputed", row_id=row_id),
        synthetic=parse_bool(row.get("synthetic"), field="synthetic", row_id=row_id),
        price_from_kzt=int(float(row["price_from_kzt"])),
        price_imputed=parse_bool(row.get("price_imputed"), field="price_imputed", row_id=row_id),
        event_formats=split_list(row.get("event_formats")),
        languages=split_list(row.get("languages")),
        max_hours=parse_optional_float(row.get("max_hours")),
        busy_dates=parse_busy_dates(row.get("busy_dates"), row_id=row_id),
        description=(row.get("description") or "").strip(),
    )


@dataclass(frozen=True)
class KnownValues:
    """Every value the dataset actually contains: normalized -> display spelling.

    Anything an LLM produces must be one of these to be used.
    """

    categories: dict[str, str]
    languages: dict[str, str]
    event_formats: dict[str, str]


def known_values(contractors: list[Contractor]) -> KnownValues:
    categories: dict[str, str] = {}
    languages: dict[str, str] = {}
    formats: dict[str, str] = {}
    for c in contractors:  # sorted by id -> first spelling wins deterministically
        for norm, display in zip(c.categories, c.categories_display):
            categories.setdefault(norm, display)
        for lang in c.languages:
            languages.setdefault(lang, lang)
        for fmt in c.event_formats:
            formats.setdefault(fmt, fmt)
    return KnownValues(
        categories=dict(sorted(categories.items())),
        languages=dict(sorted(languages.items())),
        event_formats=dict(sorted(formats.items())),
    )


def load_contractors(path: str | Path = DEFAULT_DATASET) -> list[Contractor]:
    """Parse every row; the returned list is sorted by id so file order never matters."""
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in EXPECTED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name} is missing columns: {missing}")
        contractors = [parse_row(row) for row in reader]

    ids = [c.id for c in contractors]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate contractor ids in dataset")
    return sorted(contractors, key=lambda c: c.id)
