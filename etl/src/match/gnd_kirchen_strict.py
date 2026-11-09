"""Strict plausibility check for a church <-> GND BuildingOrMemorial pairing.

Why this exists: the original matcher (gnd_match_kirchen.py) queried lobid
with wildcard patterns (preferredName:*Peter* AND preferredName:*Mitte*)
and accepted a single hit as "ok". Wildcards match substrings, so
"St. Peter (Mitte), Muenchen" was linked to "Sankt Peter und Paul
(Mittenwald)": "Mitte" is a substring of "Mittenwald" and "Peter" of
"Peter und Paul" - a different saint-pair, a different town.

A candidate now only counts when, comparing the GND preferredName
"<Widmung> (<Ort>[-<Stadtteil>])" with our own Kirche/Ort data:

  1. the dedication matches exactly (same saint names in the same order;
     "Peter" is not "Peter und Paul"; Sankt/Kirche/Baptist etc. ignored,
     inflection and compounds like "Mariahilfkapelle" tolerated),
  2. the GND place is our Ort or Gemeinde as a whole name - never a
     substring: "Moos" is not "Rohrmoos", "Aschaffenburg" is not
     "Goldbach, Aschaffenburg" - and
  3. if our Kirche text names a district ("St. Peter (Mitte)"), a GND
     candidate naming a *different* district is not accepted.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from match.kirche_ortsteil import district_candidate  # noqa: E402

_GENERIC = {
    "sankt", "st", "sanct", "heilige", "heiliger", "heiligen", "hl", "kirche", "kapelle",
    "pfarrkirche", "filialkirche", "wallfahrtskirche", "klosterkirche", "schlosskapelle",
    "schulkapelle", "friedhofskirche", "und", "der", "die", "das", "ehem", "zur", "zum",
    "alt", "alte", "alter", "neu", "neue", "baptist", "evangelist", "apostel", "taufer",
    "martyrer", "bischof", "abt", "erzengel", "stadtpfarrkirche", "pfarr", "kath", "ev",
    "evang", "evangelische", "katholische", "lutherische", "luth", "evangelisch", "katholisch",
}
_PLACE_NOISE = {"a", "am", "an", "d", "der", "im", "in", "bei", "ob", "vor", "dem", "den", "landkreis", "lkr", "kreis"}
_ALIASES = {"mariae": "maria", "marie": "maria"}
_COMPOUND_SUFFIXES = ("kapelle", "kirche", "kirchlein")


def _fold(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("é", "e"), ("è", "e")):
        text = text.replace(a, b)
    return text


def _stem(w: str) -> str:
    w = _ALIASES.get(w, w)
    for suf in ("er", "en", "es", "e", "s", "n"):
        if len(w) > 5 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z]+", " ", _fold(text)).split()


def _place_tokens(text: str) -> list[str]:
    return [w for w in _words(text) if w not in _PLACE_NOISE]


def gnd_place(preferred_name: str) -> str | None:
    """Content of the *last* top-level parenthesis, e.g. 'Hof (Saale)' in 'Kreuzkirche (Hof (Saale))'."""
    m = re.search(r"\((.*)\)\s*$", preferred_name or "")
    return m.group(1).strip() if m else None


def _dedication_key(name: str, ort_words: set[str]) -> str:
    head = name.split("(")[0]
    words = [w for w in _words(head) if w not in ort_words]
    out = []
    for w in words:
        for suf in _COMPOUND_SUFFIXES:
            if w.endswith(suf) and len(w) > len(suf) + 2:
                w = w[: -len(suf)]
                break
        if w in _GENERIC or len(w) < 3:
            continue
        out.append(_stem(_ALIASES.get(w, w)))
    if not out:  # e.g. "Friedhofskirche", "Gustav-Adolf-Gedaechtniskirche": compare the full words
        out = [_stem(w) for w in words if len(w) >= 3]
    return "".join(out)


def _place_matches(place_part: str, base: str) -> bool:
    """Whole-name equality on folded tokens; GND hyphen form '<Ort>-<Stadtteil>' also accepted."""
    p, b = _place_tokens(place_part), _place_tokens(re.sub(r"\(.*?\)", " ", base))
    if not b:
        return False
    if p == b:
        return True
    return p[: len(b)] == b or p[-len(b) :] == b


def verdict(kirche: str, ort: str | None, gemeinde: str | None, preferred_name: str) -> tuple[str, str]:
    """('pass'|'name'|'ort'|'stadtteil', reason). Only 'pass' is acceptable."""
    bases = [b for b in (ort, gemeinde) if b]
    ort_words = {w for b in bases for w in _place_tokens(b)}
    ours = _dedication_key(kirche, ort_words)
    theirs = _dedication_key(preferred_name, ort_words)
    if not ours or ours != theirs:
        return "name", f"Widmung weicht ab: '{kirche}' (Datenbank) vs. '{preferred_name}' (GND)"

    place = gnd_place(preferred_name)
    if place is None:  # format "Widmung Ortsname" without parenthesis; the Ort words were already compared away
        return ("pass", "") if any(w in _words(preferred_name) for w in ort_words) else ("ort", "GND-Eintrag nennt keinen Ort")

    district_hint = district_candidate(kirche)
    # "Neustift, Passau" / "Klingenberg, Main" / "Hof (Saale)": the part before the first comma is the place proper
    first = re.sub(r"\(.*?\)", " ", place.split(",")[0])
    rest = [s for s in place.split(",")[1:]]
    # name already carries the place ("Christuskirche Forchheim (Oberfranken)", "Bennokapelle Tuerkheim, Unterallgaeu")
    head_words = _words(preferred_name.split("(")[0].split(",")[0])
    if ort_words and ort_words <= set(head_words):
        return "pass", ""
    for base in bases:
        b_tokens = _place_tokens(re.sub(r"\(.*?\)", " ", base))
        p_tokens = _place_tokens(first)
        # "Aigen a. Inn" (ours) vs. "Aigen, Inn" (GND): place proper + river/district named after the comma
        if p_tokens and b_tokens[: len(p_tokens)] == p_tokens and len(b_tokens) > len(p_tokens):
            tail = set(b_tokens[len(p_tokens):])
            if tail and tail <= {w for r in rest for w in _place_tokens(r)}:
                return "pass", ""
        if _place_matches(first, base):
            ptok, btok = _place_tokens(first), _place_tokens(re.sub(r"\(.*?\)", " ", base))
            extra = ptok[len(btok):] if ptok[: len(btok)] == btok else ptok[: len(ptok) - len(btok)]
            if district_hint and extra:
                hint = _place_tokens(district_hint)
                if not (set(hint) & set(extra)):
                    return "stadtteil", f"Stadtteil weicht ab: '{district_hint}' (Datenbank) vs. '{place}' (GND)"
            return "pass", ""
    if district_hint and _place_matches(first, district_hint):
        if not rest or any(_place_matches(r, b) for r in rest for b in bases):
            return "pass", ""
    return "ort", f"Ort weicht ab: '{ort}' (Datenbank) vs. '{place}' (GND '{preferred_name}')"
