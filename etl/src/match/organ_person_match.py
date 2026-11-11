"""Link individual organs to a specific entry in the Personenlexikon.

Run after builders.json (with its `personen[]`) and the organ shards exist:

    cd etl/src
    <venv>/Scripts/python.exe match/organ_person_match.py

This is purely local text matching - no network calls, so unlike the
GND/BMS/Gateway-Bayern matchers there is no rate limiting and no need to
resume a partial run; it still writes a cache (etl/cache/
organ_person_matches.json) only to keep the same cache-then-merge,
review-before-commit shape as the rest of the project.

Bydaten.BAUER (`organ.bauer_name`) is free text, almost always "Nachname,
Vorname, Ort" (checked against the real data: 20175/22278 non-empty values
have exactly 2 commas). The *lemma*-level matcher (transform/bauer_match.py)
already links ~116 organs where that whole string exactly equals a Bybauer
lemma name - deliberately narrow, because several lemmata share a surname
for genuinely different people (see its docstring). This script goes one
level deeper, matching against the *individual* persons resolved from every
lemma (transform/person_parser.py), which lets a shared-surname lemma
resolve safely as long as the forename disambiguates:

    1. If BAUER's full/location-stripped text exactly matches a lemma name
       (the existing lemma-level signal) and that lemma has exactly one
       person, it's an unambiguous "sicher" match - no further check needed,
       the lemma match alone already pinned down a single person.
    2. If that lemma has *several* people (e.g. three generations of the
       same workshop under one lemma), the parsed forename must exactly
       match exactly one of them - "sicher" only when unambiguous, else
       "unsicher".
    3. If BAUER doesn't match any lemma name at all (common - most lemmata
       bundling several people are only named by surname, e.g. "Hoffmann",
       while BAUER carries the fuller "Hoffmann, Otto, Ostheim/Rhön"),
       search *all* persons database-wide by normalized surname instead,
       then require the forename to pick exactly one - same decision
       shape as step 2, just not restricted to one lemma.

Forename agreement is intentionally exact string equality (normalized for
case/whitespace), not fuzzy - lemma names collide across genuinely
different people often enough (see above) that a near-match is exactly
the kind of case that belongs in the review list, not auto-linked.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

_WS = re.compile(r"\s+")


class OrganPersonMatch(TypedDict):
    status: str  # "sicher" | "unsicher" | "keine"
    person_id: str | None  # "{lemma_id}-{person_index}"
    lemma_id: int | None
    grund: str | None


def _normalize(s: str | None) -> str:
    return _WS.sub(" ", (s or "")).strip().casefold()


def _strip_location(name: str) -> str:
    parts = [p.strip() for p in name.split(",")]
    if len(parts) >= 3:
        return ", ".join(parts[:2])
    return name.strip()


def _parse_bauer_name(raw: str) -> tuple[str, str | None]:
    """("Nachname", "Vorname" or None) from free text "Nachname[, Vorname[, Ort]]"."""
    parts = [p.strip() for p in raw.split(",")]
    nachname = parts[0]
    vorname = parts[1] if len(parts) >= 2 and parts[1] else None
    return nachname, vorname


def _flatten_persons(lemmata: list[dict]) -> list[dict]:
    persons = []
    for lemma in lemmata:
        for p in lemma.get("personen", []):
            persons.append({
                "person_id": f"{lemma['id']}-{p['index']}",
                "lemma_id": lemma["id"],
                "lemma_name": lemma["name"],
                "nachname": p.get("nachname"),
                "vorname": p.get("vorname"),
                "geburt": (p.get("lebensdaten") or {}).get("geburtsjahr"),
                "tod": (p.get("lebensdaten") or {}).get("todesjahr"),
            })
    return persons


def _window(p: dict) -> tuple[int, int] | None:
    """Years in which a person can plausibly have built an organ, from the life
    dates in the lexicon; None when the lexicon has no usable date."""
    g, t = p.get("geburt"), p.get("tod")
    if g and t:
        return g + 15, t + 3
    if g:
        return g + 15, g + 75
    if t:
        return t - 65, t + 3
    return None


def _dedupe(cands: list[dict], nachname: str) -> list[dict]:
    """The same person can sit in several lemmata (e.g. "Hoffmann" and
    "Markert" both list Otto Hoffmann, b. 1913). Identical forename+dates count
    once, represented by the lemma named after the surname."""
    groups: dict[tuple, list[dict]] = {}
    for c in cands:
        # Without any life date two same-named persons cannot be told apart
        # from two different people, so undated ones are never merged.
        undated = not c.get("geburt") and not c.get("tod")
        groups.setdefault((_normalize(c["vorname"]), c.get("geburt"), c.get("tod"), c["person_id"] if undated else None), []).append(c)
    out = []
    for members in groups.values():
        named = [m for m in members if _normalize(m["lemma_name"]) == _normalize(nachname)]
        out.append((named or members)[0] if len(named or members) == 1 or named else members[0])
    return out


def _by_year(cands: list[dict], jahr: int | None, jahr_bis: int | None) -> dict | None:
    """The one candidate whose active years contain the build year while every
    other candidate is positively ruled out by its own dates. Anything less
    (no year, a candidate without dates) is not conclusive."""
    if jahr is None:
        return None
    lo, hi = jahr, jahr_bis or jahr
    fit, ruled_out = [], 0
    for c in cands:
        w = _window(c)
        if w is None:
            return None
        if w[0] <= hi and lo <= w[1]:
            fit.append(c)
        else:
            ruled_out += 1
    return fit[0] if len(fit) == 1 and ruled_out == len(cands) - 1 else None


def _pick_by_vorname(candidates: list[dict], vorname: str | None, nachname: str = "", jahr: int | None = None,
                     jahr_bis: int | None = None) -> tuple[dict | None, str | None]:
    """Returns (unique match or None, reason if not conclusive)."""
    if len(candidates) == 1 and vorname is None:
        return candidates[0], None
    if vorname is None:
        return None, f"{len(candidates)} Personen mit diesem Nachnamen, aber kein Vorname in BAUER zum Abgleich"
    matches = [c for c in candidates if c["vorname"] and _normalize(c["vorname"]) == _normalize(vorname)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches = _dedupe(matches, nachname)
        if len(matches) == 1:
            return matches[0], None
        pick = _by_year(matches, jahr, jahr_bis)
        if pick:
            return pick, None
        return None, f"Vorname „{vorname}“ passt auf {len(matches)} Personen gleichzeitig"
    # No identical forename: BAUER may give only the first of several given
    # names ("Max" for "Max Josef"). Accepted only when the build year singles
    # out that person among *all* persons with this surname.
    first = _normalize(vorname)
    partial = [c for c in candidates if c["vorname"] and _normalize(c["vorname"]).split(" ")[0] == first]
    partial = _dedupe(partial, nachname) if partial else []
    if len(partial) == 1:
        pick = _by_year(_dedupe(candidates, nachname), jahr, jahr_bis)
        if pick and pick["person_id"] == partial[0]["person_id"]:
            return pick, None
    return None, f"Vorname „{vorname}“ passt auf keine der {len(candidates)} Personen mit diesem Nachnamen"


def match_organ(bauer_name: str, lemma_by_name: dict[str, dict], persons_by_surname: dict[str, list[dict]],
                jahr: int | None = None, jahr_bis: int | None = None) -> OrganPersonMatch:
    nachname, vorname = _parse_bauer_name(bauer_name)
    if not nachname:
        return {"status": "keine", "person_id": None, "lemma_id": None, "grund": None}

    # Step 1+2: does the (location-stripped) BAUER text match a lemma name?
    lemma = lemma_by_name.get(bauer_name) or lemma_by_name.get(_strip_location(bauer_name))
    if lemma is not None:
        lemma_persons = [p for p in persons_by_surname.get(_normalize(nachname), []) if p["lemma_id"] == lemma["id"]]
        if not lemma_persons:
            return {"status": "keine", "person_id": None, "lemma_id": lemma["id"], "grund": "Lemma hat keine aufgeloesten Personen"}
        match, grund = _pick_by_vorname(lemma_persons, vorname, nachname, jahr, jahr_bis)
        if match:
            return {"status": "sicher", "person_id": match["person_id"], "lemma_id": lemma["id"], "grund": None}
        return {"status": "unsicher", "person_id": None, "lemma_id": lemma["id"], "grund": grund}

    # Step 3: database-wide surname search, independent of any lemma-name match.
    candidates = persons_by_surname.get(_normalize(nachname), [])
    if not candidates:
        return {"status": "keine", "person_id": None, "lemma_id": None, "grund": None}
    match, grund = _pick_by_vorname(candidates, vorname, nachname, jahr, jahr_bis)
    if match:
        return {"status": "sicher", "person_id": match["person_id"], "lemma_id": match["lemma_id"], "grund": None}
    return {"status": "unsicher", "person_id": None, "lemma_id": None, "grund": grund}


def run(organs_dir: Path, builders_path: Path, cache_path: Path) -> None:
    lemmata = json.loads(builders_path.read_text(encoding="utf-8"))
    lemma_by_name = {lemma["name"]: lemma for lemma in lemmata if lemma.get("name")}
    persons = _flatten_persons(lemmata)
    persons_by_surname: dict[str, list[dict]] = {}
    for p in persons:
        if p["nachname"]:
            persons_by_surname.setdefault(_normalize(p["nachname"]), []).append(p)

    results: dict[int, OrganPersonMatch] = {}
    for shard_path in sorted(organs_dir.glob("organs-*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            if not organ.get("bauer_name"):
                continue
            j = organ.get("jahr") or {}
            results[organ["id"]] = match_organ(organ["bauer_name"], lemma_by_name, persons_by_surname, j.get("jahr"), j.get("jahr_bis"))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    counts = Counter(r["status"] for r in results.values())
    print(f"{len(results)} Orgeln mit BAUER-Text geprueft: {dict(counts)}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "organs",
        repo_root / "site" / "src" / "data" / "builders.json",
        repo_root / "etl" / "cache" / "organ_person_matches.json",
    )


if __name__ == "__main__":
    main()
