"""Match Bydaten.BAUER (free text, e.g. "Führer, Johannes, München") against
the Bybauer lexicon (e.g. "Führer, Johannes" or just "Achamer").

Checked against the real data: only exact string match, or exact match
after stripping the trailing ", <Ort>" location suffix, are trustworthy.
A rapidfuzz fallback was tested and rejected - several Bybauer entries are
different people who share a surname (e.g. four separate "Allgeyer, ..."
entries), so fuzzy surname-based matching risks linking an organ to the
wrong builder's biography. Only ~116 of 32,262 organ rows (0.36%) get a
confident match this way; Bybauer functions as a separate curated lexicon
of ~1,000 builders, not a lookup that covers most BAUER text - this is
expected, not a bug, and organ pages must not overstate the link.
"""
from __future__ import annotations

from typing import TypedDict


class BauerMatch(TypedDict):
    bauer_name: str | None
    bauer_id: int | None
    bauer_confidence: str  # "exact" | "none"


def _strip_location(name: str) -> str:
    parts = [p.strip() for p in name.split(",")]
    if len(parts) >= 3:
        return ", ".join(parts[:2])
    return name.strip()


def build_lookup(bybauer_rows: list[dict]) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for row in bybauer_rows:
        name = (row.get("ORGBAUER") or "").strip()
        if name:
            lookup[name] = row["ID"]
    return lookup


def match_bauer(raw: str | None, lookup: dict[str, int]) -> BauerMatch:
    if raw is None or not raw.strip():
        return {"bauer_name": None, "bauer_id": None, "bauer_confidence": "none"}

    name = raw.strip()
    if name in lookup:
        return {"bauer_name": name, "bauer_id": lookup[name], "bauer_confidence": "exact"}

    stripped = _strip_location(name)
    if stripped in lookup:
        return {"bauer_name": name, "bauer_id": lookup[stripped], "bauer_confidence": "exact"}

    return {"bauer_name": name, "bauer_id": None, "bauer_confidence": "none"}
