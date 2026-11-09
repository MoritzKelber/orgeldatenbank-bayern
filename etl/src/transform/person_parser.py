"""Split a Bybauer biografie entry into individual named persons.

Problem this solves: a Bybauer "lemma" is keyed by surname (the ORGBAUER
field), but its free-text BIOGRAFIE often bundles several distinct people
who share that surname - typically father/son/brother workshop successions.
The source already marks this with its own convention when it happens:

    1. Allgeyer, Johann Georg (aus Neunstadt, Werkstatt in Hofen)
    2. Allgeyer, Johann (1712-1782) (Sohn von 1.)
    3. Allgeyer, Joseph (geb. 1703) (Sohn von 1.)
    ...

This module only parses the numbered PERSON HEADER lines (name, life-date
parenthetical, family-relation parenthetical) - never the surrounding
descriptive prose, which stays attached to the lemma as a whole and keeps
being shown as-is. Attributing which sentence of shared prose belongs to
which person is not reliably automatable from the free text (e.g. the Beer
lemma lists three headers first, then one shared paragraph covering all
three) - rather than guess, we leave that prose where a human already put
it and only lift out what's mechanically unambiguous: who is named, what
life dates they carry, and how they relate to the other numbered entries.

Entries without numbering (the large majority, ~820 of 1000) become a
single person from their first line. Never discard information: every
raw parenthetical is kept in full even where it couldn't be classified.
"""
from __future__ import annotations

import re
from typing import TypedDict

_NUMBERED_HEADER = re.compile(r"^\s*(\d+|[IVXLCDM]+)\.\s+(\S.+?)\s*$")
_ROMAN = re.compile(r"^[IVXLCDM]+$")
_PAREN = re.compile(r"\(([^()]*)\)")
_RELATION = re.compile(
    r"^(Sohn|Tochter|Vater|Mutter|Bruder|Schwester|Enkel|Neffe)\s+von\s+(\d+)\.?$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\d{3,4}")
_RANGE = re.compile(r"^\s*(\d{3,4})\s*[-–]\s*(\d{1,4})\s*$")
_BIRTH_ONLY = re.compile(r"^\s*(?:geb\.?|geboren|\*)\s*(\d{3,4})\s*$", re.IGNORECASE)
_DEATH_ONLY = re.compile(r"^\s*(?:gest\.?|gestorben|verstorben|†)\D*(\d{3,4})\s*$", re.IGNORECASE)
_ROMAN_SUFFIX = re.compile(r"^(.*\S)\s+(I{1,3}|IV)\.?\s*$")
# Branch-label and provenance leakage into the "vorname" position - e.g.
# "Hofmann, Neustadt" (a workshop location, not a forename) or "Weiß,
# Johann Jakob, Polen" (the maxsplit=1 comma-split in _parse_person_header
# leaves "Johann Jakob, Polen" together, with "Polen" being where the
# person worked/came from, not part of the name). Caught here and routed
# to `beschreibung_odb` instead of being shown as if it were a forename.
_BESCHREIBUNG_KEYWORDS = re.compile(r"orgelbau|familie|werkstatt|anstalt|gesellschaft", re.IGNORECASE)
# A handful of lemmata have no biografie of their own at all - just a
# cross-reference to a different lemma that already covers the same
# builder under another spelling/name, e.g. "siehe Becker und Hiendl" or
# "= Staudenmayer?" (the source's own "probably the same as" shorthand).
# That is not a person, so it must not become one in the Person layer -
# matched line.
_CROSS_REFERENCE_ONLY = re.compile(r"^\s*(?:siehe\s+.+|=\s*.+)\s*$", re.IGNORECASE)


class Lebensdaten(TypedDict):
    raw: list[str]
    geburtsjahr: int | None
    todesjahr: int | None


class Beziehung(TypedDict):
    typ: str
    bezug_index: int


class Person(TypedDict):
    index: int
    name_raw: str
    nachname: str | None
    vorname: str | None
    namenszusatz: str | None  # roman-numeral generation suffix, e.g. "I.", "II."
    beschreibung_odb: str | None  # branch-label/provenance text that leaked into the name field
    lebensdaten: Lebensdaten
    beziehung: Beziehung | None
    anmerkungen_kurz: list[str]  # unclassified parenthetical notes from the header line


def _expand_two_digit_end(start: int, end_part: str) -> int:
    if len(end_part) >= len(str(start)):
        return int(end_part)
    prefix_len = len(str(start)) - len(end_part)
    return int(str(start)[:prefix_len] + end_part)


def _parse_lebensdaten_fragment(fragment: str) -> tuple[int | None, int | None]:
    frag = fragment.strip()
    m = _RANGE.match(frag)
    if m:
        start = int(m.group(1))
        return start, _expand_two_digit_end(start, m.group(2))
    m = _BIRTH_ONLY.match(frag)
    if m:
        return int(m.group(1)), None
    m = _DEATH_ONLY.match(frag)
    if m:
        return None, int(m.group(1))
    years = _YEAR.findall(frag)
    if len(years) == 1:
        # Ambiguous single year (e.g. "um 1710 nachweisbar") - too unreliable
        # to label birth vs. death, so left unset; the raw text is kept.
        return None, None
    if len(years) >= 2:
        return int(years[0]), int(years[1])
    return None, None


def _split_name_and_parens(header: str) -> tuple[str, list[str]]:
    parens = _PAREN.findall(header)
    name_part = _PAREN.sub("", header).strip()
    return name_part, [p.strip() for p in parens if p.strip()]


def _split_vorname_beschreibung(vorname: str) -> tuple[str | None, str | None]:
    """(real forename or None, leaked description or None)."""
    if _BESCHREIBUNG_KEYWORDS.search(vorname):
        return None, vorname
    if "," in vorname:
        core, rest = (part.strip() for part in vorname.rsplit(",", 1))
        if core and rest and not re.search(r"\d", rest) and len(rest.split()) <= 6:
            return core, rest
    return vorname, None


def _parse_person_header(index: int, header: str) -> Person:
    name_part, parens = _split_name_and_parens(header)

    nachname, vorname = None, None
    if "," in name_part:
        nachname, vorname = (part.strip() or None for part in name_part.split(",", 1))
    else:
        nachname = name_part or None

    beschreibung_odb = None
    if vorname:
        vorname, beschreibung_odb = _split_vorname_beschreibung(vorname)

    namenszusatz = None
    if vorname:
        m = _ROMAN_SUFFIX.match(vorname)
        if m:
            vorname, namenszusatz = m.group(1), m.group(2) + "."

    lebensdaten_raw: list[str] = []
    geburtsjahr: int | None = None
    todesjahr: int | None = None
    beziehung: Beziehung | None = None
    anmerkungen_kurz: list[str] = []

    for p in parens:
        rel = _RELATION.match(p)
        if rel:
            beziehung = {"typ": rel.group(1).lower(), "bezug_index": int(rel.group(2))}
            continue
        if _YEAR.search(p) or "unbekannt" in p.lower():
            lebensdaten_raw.append(p)
            if "unbekannt" not in p.lower():
                g, t = _parse_lebensdaten_fragment(p)
                geburtsjahr = geburtsjahr or g
                todesjahr = todesjahr or t
            continue
        anmerkungen_kurz.append(p)

    return {
        "index": index,
        "name_raw": header,
        "nachname": nachname,
        "vorname": vorname,
        "namenszusatz": namenszusatz,
        "beschreibung_odb": beschreibung_odb,
        "lebensdaten": {"raw": lebensdaten_raw, "geburtsjahr": geburtsjahr, "todesjahr": todesjahr},
        "beziehung": beziehung,
        "anmerkungen_kurz": anmerkungen_kurz,
    }


def parse_persons(biografie: str | None, fallback_name: str | None = None) -> list[Person]:
    """Flatten a (possibly two-level) numbered biografie into a person list.

    Some lemmas bundle several *unrelated* same-surname family branches,
    each marked with a Roman numeral, with Arabic numbering restarting at
    1 inside every branch (see e.g. the "Weiss" or "Hofmann" lemmata - three
    independent workshops, each internally numbered 1..N). A Roman header
    either embeds a person directly ("I. Hoffmann, H. C.") or is a pure
    branch label with no comma ("II. Hofmann, Neustadt" - then "Neustadt"
    is a workshop location, not a forename; left as-is since GND matching
    simply won't find anyone and nothing is lost, just imprecisely labelled).

    `index` on the returned persons is a simple running count, unique
    within the lemma regardless of how the source renumbered within each
    branch; `beziehung.bezug_index` is remapped from the source's
    branch-local reference (e.g. "Sohn von 1." meaning branch-local person
    1) to that same running count, since otherwise "1." would be
    ambiguous across branches. The requirement that header text start
    with an uppercase letter filters out running prose that happens to
    start a line with "<number>. " while actually continuing an earlier
    person's description (e.g. "7. war 1945/46 Betriebsleiter ...").
    """
    if not biografie or not biografie.strip():
        # No biografie text at all - but the lemma's own name (the ORGBAUER
        # surname) still identifies a real builder, e.g. "Gerdner" with an
        # empty biografie but one linked organ. Without this fallback such
        # lemmata produced zero persons and - after the Erbauer-Lexikon
        # pages were removed from the public site - became unreachable.
        if fallback_name and fallback_name.strip():
            return [_parse_person_header(1, fallback_name.strip())]
        return []

    stripped = biografie.strip()
    if len(stripped.splitlines()) == 1 and _CROSS_REFERENCE_ONLY.match(stripped):
        return []

    lines = biografie.splitlines()
    raw_headers: list[tuple[str, str]] = []
    for line in lines:
        m = _NUMBERED_HEADER.match(line)
        if m and m.group(2)[:1].isupper():
            raw_headers.append((m.group(1), m.group(2)))

    if not raw_headers:
        first_line = next((l.strip() for l in lines if l.strip()), "")
        if not first_line:
            return []
        return [_parse_person_header(1, first_line)]

    persons: list[Person] = []
    local_to_global: dict[str, int] = {}
    for raw_key, text in raw_headers:
        if _ROMAN.match(raw_key):
            local_to_global = {}  # new branch: local Arabic numbering restarts
            if "," not in text:
                continue  # pure branch label (e.g. "Weiß" / "Hofmann, Neustadt"), not a person
        person = _parse_person_header(len(persons) + 1, text)
        local_to_global[raw_key] = person["index"]
        if person["beziehung"]:
            ref = str(person["beziehung"]["bezug_index"])
            person["beziehung"]["bezug_index"] = local_to_global.get(ref, person["beziehung"]["bezug_index"])
        persons.append(person)

    return persons
