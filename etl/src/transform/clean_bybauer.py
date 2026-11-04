"""Clean Bybauer rows into the builder-lexicon record shape.

AUSWAHL is a leftover Access-form "selected" checkbox, not real data, and
is dropped. organ_ids is filled in later by the pipeline once organs have
been matched (see bauer_match.py).

Each lemma is keyed by surname but its BIOGRAFIE often bundles several
distinct people sharing that name (father/son workshop successions) -
`personen` makes those individuals explicit; see transform/person_parser.py
for why that parsing deliberately stops at the name/life-date/relation
level and leaves the surrounding prose attached to the lemma as a whole.
`gnd` on each person is filled in later, once match/gnd_match.py and
match/apply_gnd_matches.py have run (same cache-then-merge pattern as the
geocoding step).
"""
from __future__ import annotations

from .person_parser import parse_persons


def clean_bybauer_row(row: dict) -> dict:
    name = (row.get("ORGBAUER") or "").strip() or None
    biografie = (row.get("BIOGRAFIE") or "").strip() or None
    personen = parse_persons(biografie)
    for person in personen:
        person["gnd"] = None
    return {
        "id": row["ID"],
        "name": name,
        "biografie": biografie,
        "personen": personen,
        "organ_ids": [],
    }
