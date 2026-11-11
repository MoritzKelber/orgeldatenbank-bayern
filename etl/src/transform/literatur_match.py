"""Reconcile Literatur.LIT citation strings against the Byliteratur master
catalog (keyed by KURZTITEL).

Checked against the real data: LIT is usually KURZTITEL plus a page/opus
suffix appended, e.g. KURZTITEL "FS Abenberg (1997)" vs LIT
"FS Abenberg (1997), S.4". Page suffixes come in many shapes ("S.4",
"S.158, 213", "S.34-36", "S.12 ff.", "Nr.3, 7"), so a LIT value is matched by
looking for the longest prefix that is a known KURZTITEL and only accepting it
when the rest looks like a page/part addendum.

Serial works are catalogued once with placeholders, e.g. "Kraus, Diözese
Regensburg [Band] [Jahr]" or "Orgelspiegel [Nummer] ([Jahr])", while LIT names
the concrete part ("Kraus, Diözese Regensburg 4 (1987)"). Those are matched by
turning each placeholder KURZTITEL into a pattern (confidence "serie").

A residual genuinely has no Byliteratur entry at all (personal communications
like "Mitteilung M. Hohmann, Heideck (2000)", web pages) - that is expected,
not a matching failure, and those citations are still always shown as plain
text; only the hyperlink to a Byliteratur detail page depends on match
confidence.
"""
from __future__ import annotations

import re
from typing import TypedDict

from rapidfuzz import fuzz, process

# Everything after the KURZTITEL that is only a locator: pages, columns,
# numbers, "ff.", ranges, roman part numbers in parentheses ...
_ADDENDUM_RE = re.compile(
    r"""^\s*[,;.]?\s*
        (?:(?:S|Sp|Bl|Nr|Bd|Abb|Tab|Taf|Fig|op|Heft|H)\.?\s*)?
        [\dIVXLC][\dIVXLC\s,;/\-–.+ff()a-z]*$""",
    re.IGNORECASE | re.VERBOSE,
)
_SUFFIX_RE = re.compile(
    r"[,.]\s*(S\.\s*[0-9]+(/[0-9]+)?(\s*f{1,2}\.?)?|op\.\s*[0-9]+|Nr\.\s*[0-9]+)\s*$",
    re.IGNORECASE,
)

FUZZY_THRESHOLD = 95

_PLACEHOLDER = {
    "[Band]": r"(?:[IVXLC]+|\d+)",
    "[Teil]": r"(?:[IVXLC]+|\d+)",
    "[Nr.]": r"\d+",
    "[Nummer]": r"\d+",
    "[Jahr]": r"\(?\d{4}(?:[/\-–]\d{2,4})?\)?",
}


class LiteraturMatch(TypedDict):
    kurztitel: str | None
    confidence: str  # "exact" | "normalisiert" | "serie" | "fuzzy" | "keine"


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


def _template_patterns(kurztitel_list: list[str]) -> list[tuple[re.Pattern, str]]:
    """[(regex, kurztitel)] for every KURZTITEL containing a [placeholder]
    that stands for a part/volume/number of a serial work."""
    out = []
    for k in kurztitel_list:
        if not any(p in k for p in _PLACEHOLDER) or k.startswith("Mitteilung"):
            continue
        pat = re.escape(k)
        # A parenthesised year next to a part placeholder ("[Teil] (1975/76)")
        # names the whole run, not one part: accept any year there.
        pat = re.sub(r"\\\(\d{4}(?:/\d{2,4})?\\\)$", r"\\(\\d{4}(?:[/\\-–]\\d{2,4})?\\)", pat) if re.search(r"\\\[(?:Teil|Band|Nr\\\.|Nummer)\\\]", pat) else pat
        for ph, rx in _PLACEHOLDER.items():
            pat = pat.replace(re.escape(ph), rx)
        # "([Jahr])" -> "(1987)": the parentheses already sit in the pattern
        pat = pat.replace(r"\(\(?", r"\(").replace(r"\)?\)", r"\)")
        out.append((re.compile(r"^" + pat + r"(?=$|[\s,;.])", re.IGNORECASE), k))
    return out


_TEMPLATES: dict[int, list[tuple[re.Pattern, str]]] = {}


def _templates(kurztitel_list: list[str]) -> list[tuple[re.Pattern, str]]:
    key = id(kurztitel_list)
    if key not in _TEMPLATES:
        _TEMPLATES[key] = _template_patterns(kurztitel_list)
    return _TEMPLATES[key]


def _prefix_match(text: str, kurztitel_set: set[str]) -> str | None:
    """Longest prefix of `text` that is a KURZTITEL and is followed only by a
    locator addendum (or nothing)."""
    best = None
    for m in re.finditer(r"[)\]]|(?<=\w)(?=[,;.]\s)", text):
        end = m.end() if text[m.start()] in ")]" else m.start()
        head = text[:end].rstrip()
        if head in kurztitel_set and _ADDENDUM_RE.match(text[end:] or "0"):
            best = head
    if text in kurztitel_set:
        best = text
    return best


def match_literatur(lit: str | None, kurztitel_set: set[str], kurztitel_list: list[str]) -> LiteraturMatch:
    if lit is None or not lit.strip():
        return {"kurztitel": None, "confidence": "keine"}

    text = lit.strip()
    if text in kurztitel_set:
        return {"kurztitel": text, "confidence": "exact"}

    stripped = _strip_suffix(text)
    if stripped in kurztitel_set:
        return {"kurztitel": stripped, "confidence": "normalisiert"}

    head = _prefix_match(text, kurztitel_set)
    if head:
        return {"kurztitel": head, "confidence": "normalisiert"}

    for rx, k in _templates(kurztitel_list):
        m = rx.match(text)
        if m and _ADDENDUM_RE.match(text[m.end():] or "0"):
            return {"kurztitel": k, "confidence": "serie"}

    match = process.extractOne(stripped, kurztitel_list, scorer=fuzz.ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        return {"kurztitel": match[0], "confidence": "fuzzy"}

    return {"kurztitel": None, "confidence": "keine"}
