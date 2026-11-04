"""Reconcile Literatur.LIT citation strings against the Byliteratur master
catalog (keyed by KURZTITEL).

Checked against the real data: LIT is usually KURZTITEL plus a page/opus
suffix appended, e.g. KURZTITEL "FS Abenberg (1997)" vs LIT
"FS Abenberg (1997), S.4". A small residual (~20%) genuinely has no
Byliteratur entry at all (personal communications like "Mitteilung M.
Hohmann, Heideck (2000)", or multi-page lists like "S.34, 53") - that is
expected, not a matching failure, and those citations are still always
shown as plain text; only the hyperlink to a Byliteratur detail page
depends on match confidence.
"""
from __future__ import annotations

import re
from typing import TypedDict

from rapidfuzz import fuzz, process

_SUFFIX_RE = re.compile(
    r"[,.]\s*(S\.\s*[0-9]+(/[0-9]+)?(\s*f{1,2}\.?)?|op\.\s*[0-9]+|Nr\.\s*[0-9]+)\s*$",
    re.IGNORECASE,
)

FUZZY_THRESHOLD = 95


class LiteraturMatch(TypedDict):
    kurztitel: str | None
    confidence: str  # "exact" | "normalisiert" | "fuzzy" | "keine"


def _strip_suffix(text: str) -> str:
    previous = text
    while True:
        updated = _SUFFIX_RE.sub("", previous).strip()
        if updated == previous:
            return updated
        previous = updated


def build_lookup(byliteratur_rows: list[dict]) -> tuple[set[str], list[str]]:
    titles = [row["KURZTITEL"].strip() for row in byliteratur_rows if row.get("KURZTITEL")]
    return set(titles), titles


def match_literatur(lit: str | None, kurztitel_set: set[str], kurztitel_list: list[str]) -> LiteraturMatch:
    if lit is None or not lit.strip():
        return {"kurztitel": None, "confidence": "keine"}

    text = lit.strip()
    if text in kurztitel_set:
        return {"kurztitel": text, "confidence": "exact"}

    stripped = _strip_suffix(text)
    if stripped in kurztitel_set:
        return {"kurztitel": stripped, "confidence": "normalisiert"}

    match = process.extractOne(stripped, kurztitel_list, scorer=fuzz.ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        return {"kurztitel": match[0], "confidence": "fuzzy"}

    return {"kurztitel": None, "confidence": "keine"}
