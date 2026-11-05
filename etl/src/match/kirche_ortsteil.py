"""Tell a city-district name apart from a building-type/status note in parentheses.

The organ database's Kirche field often has a parenthetical, but it means
two very different things depending on which: a disambiguating district
name ("St. Johann Baptist (Solln)" - Solln is a Munich district) or a
building-type/status note ("St. Martin (Klosterkirche)" - "monastery
church", not a place at all). match/gnd_match_kirchen.py originally
discarded every parenthetical outright, which (a) lost real
disambiguating information for city churches and (b) is exactly why GND
itself needs it: GND catalogs urban churches as "Name (Stadt-Stadtteil)",
e.g. "Sankt Wolfgang (München-Haidhausen)" - searching with just the
city name ("München") returns every church in a 1.5-million-person city
and stays stuck on "unsicher", while the district name alone is usually
unique.

This classifies by exclusion: a fixed list of known building types,
religious orders, and status words (collected by frequency-surveying
every distinct parenthetical in the dataset) is treated as "not a
place"; anything else is tried as a district name candidate.
"""
from __future__ import annotations

import re

_PREFIXES = ("ehem", "alt", "neu", "obere", "untere", "äußere", "innere")

_SUBSTRINGS = (
    "kirche", "kapelle", "kloster", "stift", "propstei", "seminar", "abtei",
    "spital", "schloss", "schloß", "dom", "münster", "basilika", "simultan",
    "profaniert", "expositur", "krankenhaus", "altenheim", "diakoniewerk",
    "pfarre",
)

_ORDERS = (
    "benediktiner", "franziskaner", "zisterzienser", "dominikaner",
    "augustiner", "kapuziner", "karmelit", "jesuit", "prämonstratenser",
    "praemonstratenser", "minoriten", "birgittinnen", "ursulinen",
    "salesianer", "chorherren", "fräulein", "schwestern", "deutschorden",
)

_EXACT = {"kp", "wallfahrt", "deutsch-ref.", "altkatholisch", "bürgersaal"}


def is_building_qualifier(paren: str) -> bool:
    text = paren.strip().lower()
    if not text or text.isdigit():
        return True
    if text in _EXACT:
        return True
    if any(text.startswith(p) for p in _PREFIXES):
        return True
    if any(s in text for s in _SUBSTRINGS):
        return True
    if any(o in text for o in _ORDERS):
        return True
    return False


def district_candidate(kirche: str) -> str | None:
    """The parenthetical content, if it looks like a real place/district name."""
    m = re.search(r"\(([^()]*)\)", kirche)
    if not m:
        return None
    paren = m.group(1).strip()
    if not paren or is_building_qualifier(paren):
        return None
    return paren
