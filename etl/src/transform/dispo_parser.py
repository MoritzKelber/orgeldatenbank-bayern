"""Parse the free-text Bydaten.DISPO field into a structured shape.

Checked against the real data (10,902 of 32,262 organs have non-empty
DISPO text): it is written as a sequence of lines of the form

    LABEL (optional qualifier): item, item, item, ...

e.g. "HAUPTWERK (1.Man.): Bourdon 16', Principal 8', ..." or
"PEDAL: Subbaß 16'". Two label families are near-universal metadata, not
stop lists, and get their own fields instead of becoming a "section":
QUELLE (source citation, ~98% of non-empty DISPO) and
BEMERKUNGEN/BEMERKUNG/KOMMENTAR (free remark). KOPPELN/KOPPEL/SPIELHILFEN/
"KOPPELN UND SPIELHILFEN" is couplers/playing aids, kept as its own item
list rather than mixed into the manual/pedal sections.

Casing of labels is inconsistent in the source ("HAUPTWERK" vs
"Hauptwerk (1.Man. C-a'''):" vs "1. Manual:") so label matching is
case-insensitive and otherwise permissive - anything "label: items" that
isn't recognized metadata becomes a generic stop-list section under its
own (verbatim-cased) name. Lines without a colon, or anything that
doesn't fit, go to extra_notes - never dropped.
"""
from __future__ import annotations

import re
from typing import TypedDict

_LINE_RE = re.compile(r"^\s*([^:\r\n]{1,60}?)\s*:\s*(.*)$")
_TRAILING_QUALIFIER_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<qualifier>[^()]*)\)\s*$")

_QUELLE_LABELS = {"QUELLE"}
_BEMERKUNG_LABELS = {"BEMERKUNGEN", "BEMERKUNG", "KOMMENTAR"}
_KOPPELN_LABELS = {"KOPPELN UND SPIELHILFEN", "KOPPELN", "KOPPEL", "SPIELHILFEN"}


class DispoSection(TypedDict):
    name: str
    qualifier: str | None
    items: list[str]


class Dispo(TypedDict):
    raw: str | None
    parsed: bool
    sections: list[DispoSection]
    koppeln: list[str]
    bemerkungen: str | None
    quelle: str | None
    extra_notes: list[str]


def _split_items(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _split_name_qualifier(label: str) -> tuple[str, str | None]:
    m = _TRAILING_QUALIFIER_RE.match(label.strip())
    if m and m.group("name"):
        return m.group("name").strip(), m.group("qualifier").strip()
    return label.strip(), None


def parse_dispo(raw: str | None) -> Dispo:
    result: Dispo = {
        "raw": raw,
        "parsed": False,
        "sections": [],
        "koppeln": [],
        "bemerkungen": None,
        "quelle": None,
        "extra_notes": [],
    }
    if raw is None or raw.strip() == "":
        return result

    lines = raw.replace("\r\n", "\n").split("\n")
    bemerkungen_parts: list[str] = []

    for line in lines:
        if not line.strip():
            continue
        m = _LINE_RE.match(line)
        if not m:
            result["extra_notes"].append(line.strip())
            continue

        label, rest = m.group(1), m.group(2)
        name, qualifier = _split_name_qualifier(label)
        key = name.strip().upper()

        if key in _QUELLE_LABELS:
            result["quelle"] = rest.strip() or result["quelle"]
        elif key in _BEMERKUNG_LABELS:
            if rest.strip():
                bemerkungen_parts.append(rest.strip())
        elif key in _KOPPELN_LABELS:
            result["koppeln"].extend(_split_items(rest))
        else:
            result["sections"].append({"name": name, "qualifier": qualifier, "items": _split_items(rest)})

    if bemerkungen_parts:
        result["bemerkungen"] = "\n".join(bemerkungen_parts)

    result["parsed"] = len(result["sections"]) >= 2
    return result
