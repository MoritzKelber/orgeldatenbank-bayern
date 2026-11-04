"""Clean the Bydaten.JAHR free-text year field.

Real data (checked against the full 32,262-row table) uses a historian's
shorthand, inconsistently as suffix OR prefix:
    "1997="     -> exact/confirmed year 1997
    "1500"      -> plain year, no qualifier
    "1500<"  "<1500"   -> vor 1500 (before)
    "1500>"             -> nach 1500 (after)
    "1500<>" "<>1500"   -> um 1500 (circa)
    "1442-44" "1424/42" -> a range (dash or slash)
    "?"                  -> unknown
    "" / None             -> not recorded

Never discard information: jahr_raw always keeps the original string, and
unparseable values fall back to qualifier "unbekannt" rather than raising.
"""
from __future__ import annotations

import re
from typing import TypedDict

_EXACT = re.compile(r"^\s*(\d{3,4})=\s*$")
_PLAIN = re.compile(r"^\s*(\d{3,4})\s*$")
_SUFFIX_CIRCA = re.compile(r"^\s*(\d{3,4})\s*<>\s*$")
_SUFFIX_BEFORE = re.compile(r"^\s*(\d{3,4})\s*<\s*$")
_SUFFIX_AFTER = re.compile(r"^\s*(\d{3,4})\s*>\s*$")
_PREFIX_CIRCA = re.compile(r"^\s*<>\s*(\d{3,4})\s*$")
_PREFIX_BEFORE = re.compile(r"^\s*<\s*(\d{3,4})\s*$")
_RANGE = re.compile(r"^\s*(\d{3,4})\s*[-/]\s*(\d{1,4})\s*$")


class Jahr(TypedDict):
    jahr_raw: str | None
    jahr: int | None
    jahr_bis: int | None
    qualifier: str  # "exakt" | "vor" | "nach" | "um" | "bereich" | "unbekannt" | "fehlt"


def _expand_range_end(start: int, end_part: str) -> int:
    """'1442-44' -> end=44 means 1444, not 44."""
    if len(end_part) >= len(str(start)):
        return int(end_part)
    prefix_len = len(str(start)) - len(end_part)
    return int(str(start)[:prefix_len] + end_part)


def parse_jahr(raw: str | None) -> Jahr:
    if raw is None or raw.strip() == "":
        return {"jahr_raw": raw, "jahr": None, "jahr_bis": None, "qualifier": "fehlt"}

    text = raw.strip()

    if text == "?":
        return {"jahr_raw": raw, "jahr": None, "jahr_bis": None, "qualifier": "unbekannt"}

    for pattern, qualifier in (
        (_EXACT, "exakt"),
        (_PLAIN, "exakt"),
    ):
        m = pattern.match(text)
        if m:
            return {"jahr_raw": raw, "jahr": int(m.group(1)), "jahr_bis": None, "qualifier": qualifier}

    for pattern in (_SUFFIX_CIRCA, _PREFIX_CIRCA):
        m = pattern.match(text)
        if m:
            return {"jahr_raw": raw, "jahr": int(m.group(1)), "jahr_bis": None, "qualifier": "um"}

    for pattern in (_SUFFIX_BEFORE, _PREFIX_BEFORE):
        m = pattern.match(text)
        if m:
            return {"jahr_raw": raw, "jahr": int(m.group(1)), "jahr_bis": None, "qualifier": "vor"}

    m = _SUFFIX_AFTER.match(text)
    if m:
        return {"jahr_raw": raw, "jahr": int(m.group(1)), "jahr_bis": None, "qualifier": "nach"}

    m = _RANGE.match(text)
    if m:
        start = int(m.group(1))
        end = _expand_range_end(start, m.group(2))
        return {"jahr_raw": raw, "jahr": start, "jahr_bis": end, "qualifier": "bereich"}

    return {"jahr_raw": raw, "jahr": None, "jahr_bis": None, "qualifier": "unbekannt"}


def format_jahr(jahr: Jahr) -> str | None:
    """Human-readable display string, or None when there's nothing to show."""
    qualifier = jahr["qualifier"]
    if qualifier == "fehlt":
        return None
    if qualifier == "unbekannt":
        return jahr["jahr_raw"]
    if qualifier == "exakt":
        return str(jahr["jahr"])
    if qualifier == "vor":
        return f"vor {jahr['jahr']}"
    if qualifier == "nach":
        return f"nach {jahr['jahr']}"
    if qualifier == "um":
        return f"um {jahr['jahr']}"
    if qualifier == "bereich":
        return f"{jahr['jahr']}–{jahr['jahr_bis']}"
    return jahr["jahr_raw"]
