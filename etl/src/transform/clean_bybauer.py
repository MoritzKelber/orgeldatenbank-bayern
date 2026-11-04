"""Clean Bybauer rows into the builder-lexicon record shape.

AUSWAHL is a leftover Access-form "selected" checkbox, not real data, and
is dropped. organ_ids is filled in later by the pipeline once organs have
been matched (see bauer_match.py).
"""
from __future__ import annotations


def clean_bybauer_row(row: dict) -> dict:
    name = (row.get("ORGBAUER") or "").strip() or None
    biografie = (row.get("BIOGRAFIE") or "").strip() or None
    return {
        "id": row["ID"],
        "name": name,
        "biografie": biografie,
        "organ_ids": [],
    }
