"""Build the literature catalog and per-organ citation lists.

Byliteratur has no numeric ID column - KURZTITEL is the natural key, so
each catalog entry gets a generated slug (for /literatur/[slug]/) with
collision-suffixing in the rare case two titles slugify the same.
"""
from __future__ import annotations

from collections import defaultdict

from .literatur_match import build_lookup, match_literatur
from .slug import slugify


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_literature_catalog(byliteratur_rows: list[dict], bystichworte_rows: list[dict]) -> dict:
    """Returns {kurztitel: catalog_entry}, each entry carrying its slug."""
    keywords_by_title: dict[str, list[dict]] = defaultdict(list)
    for row in bystichworte_rows:
        kurztitel = _str_or_none(row.get("KURZTITEL"))
        if not kurztitel:
            continue
        keywords_by_title[kurztitel].append(
            {"stichwort": _str_or_none(row.get("STICHW")), "bemerkung": _str_or_none(row.get("BEM"))}
        )

    catalog: dict[str, dict] = {}
    seen_slugs: set[str] = set()
    for row in byliteratur_rows:
        kurztitel = _str_or_none(row.get("KURZTITEL"))
        if not kurztitel:
            continue
        slug = slugify(kurztitel)
        base_slug = slug
        n = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        seen_slugs.add(slug)

        catalog[kurztitel] = {
            "slug": slug,
            "kurztitel": kurztitel,
            "autor": _str_or_none(row.get("AUTOR")),
            "titel": _str_or_none(row.get("TITEL")),
            "biblio": _str_or_none(row.get("BIBLIO")),
            "vorhanden": _str_or_none(row.get("VORHANDEN")),
            "abstract": _str_or_none(row.get("ABSTRACT")),
            "keywords": keywords_by_title.get(kurztitel, []),
            "organ_ids": [],
        }
    return catalog


def build_organ_literature(literatur_rows: list[dict], catalog: dict[str, dict]) -> dict[int, list[dict]]:
    """Returns {organ_id: [citation, ...]}, sorted by LitNo, and fills
    catalog[...]["organ_ids"] in place as a side effect."""
    kurztitel_set, kurztitel_list = build_lookup([{"KURZTITEL": k} for k in catalog])

    by_organ: dict[int, list[dict]] = defaultdict(list)
    rows_sorted = sorted(literatur_rows, key=lambda r: (r["IDParent"], r.get("LitNo") or 0))
    for row in rows_sorted:
        organ_id = row["IDParent"]
        lit_text = _str_or_none(row.get("LIT"))
        match = match_literatur(lit_text, kurztitel_set, kurztitel_list)
        citation = {
            "lit": lit_text,
            "disp": bool(row.get("DISP")),
            "abb": bool(row.get("ABB")),
            "kurztitel": match["kurztitel"],
            "confidence": match["confidence"],
            "slug": catalog[match["kurztitel"]]["slug"] if match["kurztitel"] else None,
        }
        by_organ[organ_id].append(citation)
        if match["kurztitel"]:
            catalog[match["kurztitel"]]["organ_ids"].append(organ_id)

    return by_organ
