"""Match parsed builder persons against the GND (Gemeinsame Normdatei) via lobid.org.

Run after the builder/person data has been built:

    cd etl/src
    <venv>/Scripts/python.exe match/gnd_match.py

For each person (see transform/person_parser.py), queries lobid's GND search
API, scores candidates by name similarity and life-date compatibility, and
picks a match only when confident. Two query tiers:

1. Surname + the GND "Orgelbauer" occupation label - the precise, preferred
   query. Catches organ builders GND already classifies as such.
2. If that returns nothing: surname + forename, no occupation filter, but
   the candidate is only accepted if its own occupation list mentions an
   organ/instrument-building profession - recovers builders GND tagged
   under a related label without opening the door to same-name unrelated
   people.

Firms/collectives (e.g. "Albers & Wiggering") are skipped outright - GND
person records can't represent them, and querying would only risk a
spurious match. Rate-limited politely; lobid publishes no hard limit, but
~3 requests/second is a reasonable, well-behaved pace for ~1,600 lookups.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import TypedDict

import requests
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from transform.person_parser import Person  # noqa: E402

LOBID_URL = "https://lobid.org/gnd/search"
USER_AGENT = "orgeldatenbank-bayern-gnd-matcher/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
REQUEST_INTERVAL_SECONDS = 0.35
NAME_SCORE_THRESHOLD = 80  # rapidfuzz token_sort_ratio, 0-100
FIRM_PATTERN = re.compile(r"&| und |\bGesellschaft\b|\bGmbH\b|\bFirma\b", re.IGNORECASE)
_GND_YEAR = re.compile(r"\d{3,4}")


class GndMatch(TypedDict):
    status: str  # "ok" | "unsicher" | "keine" | "nicht_zutreffend"
    gnd_id: str | None
    url: str | None
    preferred_name: str | None
    geburtsjahr: int | None
    todesjahr: int | None
    name_score: float | None
    candidates_considered: int
    grund: str | None  # populated for "unsicher"


def _gnd_year(dates: list[str] | None) -> int | None:
    if not dates:
        return None
    m = _GND_YEAR.search(dates[0])
    return int(m.group(0)) if m else None


def _query(params: dict, attempt: int = 1) -> list[dict]:
    try:
        response = requests.get(
            LOBID_URL,
            params={**params, "format": "json", "size": 20},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("member", [])
    except requests.RequestException:
        if attempt >= 4:
            raise
        time.sleep(2 ** attempt)  # transient network hiccups shouldn't kill a ~15min run
        return _query(params, attempt + 1)


def _name_score(person: Person, candidate: dict) -> float:
    ours = f"{person.get('vorname') or ''} {person.get('nachname') or ''}".strip()
    theirs = candidate.get("preferredName") or ""
    return fuzz.token_sort_ratio(ours.lower(), theirs.lower())


def _dates_compatible(person: Person, candidate: dict) -> bool | None:
    """True/False if both sides have a year to compare, None if we can't tell."""
    our_geb = person["lebensdaten"]["geburtsjahr"]
    our_tod = person["lebensdaten"]["todesjahr"]
    their_geb = _gnd_year(candidate.get("dateOfBirth"))
    their_tod = _gnd_year(candidate.get("dateOfDeath"))

    checks = []
    if our_geb and their_geb:
        checks.append(abs(our_geb - their_geb) <= 2)
    if our_tod and their_tod:
        checks.append(abs(our_tod - their_tod) <= 2)
    if not checks:
        return None
    return all(checks)


def _is_organ_related(candidate: dict) -> bool:
    labels = " ".join(p.get("label", "") for p in candidate.get("professionOrOccupation", []))
    return bool(re.search(r"Orgel|Musikinstrumentenbauer", labels, re.IGNORECASE))


def match_person(person: Person) -> GndMatch:
    nachname = person.get("nachname") or ""
    vorname = person.get("vorname")

    if not nachname or FIRM_PATTERN.search(nachname):
        return {
            "status": "nicht_zutreffend", "gnd_id": None, "url": None, "preferred_name": None,
            "geburtsjahr": None, "todesjahr": None, "name_score": None,
            "candidates_considered": 0, "grund": "Firma/Kollektiv, keine Personensuche",
        }

    query = f'preferredName:"{nachname}" AND professionOrOccupation.label:Orgelbauer'
    candidates = _query({"q": query})
    tier = 1
    if not candidates and vorname:
        time.sleep(REQUEST_INTERVAL_SECONDS)
        candidates = [
            c for c in _query({"q": f'preferredName:"{nachname} {vorname}"'}) if _is_organ_related(c)
        ]
        tier = 2

    if not candidates:
        return {
            "status": "keine", "gnd_id": None, "url": None, "preferred_name": None,
            "geburtsjahr": None, "todesjahr": None, "name_score": None,
            "candidates_considered": 0, "grund": None,
        }

    scored = sorted(
        ({"c": c, "score": _name_score(person, c), "dates_ok": _dates_compatible(person, c)} for c in candidates),
        key=lambda s: s["score"],
        reverse=True,
    )
    best = scored[0]

    close_runners_up = [s for s in scored[1:] if s["score"] >= best["score"] - 5]

    def _build(status: str, grund: str | None) -> GndMatch:
        c = best["c"]
        return {
            "status": status,
            "gnd_id": c.get("gndIdentifier"),
            "url": c.get("id"),
            "preferred_name": c.get("preferredName"),
            "geburtsjahr": _gnd_year(c.get("dateOfBirth")),
            "todesjahr": _gnd_year(c.get("dateOfDeath")),
            "name_score": best["score"],
            "candidates_considered": len(candidates),
            "grund": grund,
        }

    if best["score"] < NAME_SCORE_THRESHOLD:
        return _build("keine", None)

    if best["dates_ok"] is False:
        return _build("unsicher", "Namens-Treffer, aber Lebensdaten passen nicht zur Quelle")

    if close_runners_up:
        return _build(
            "unsicher",
            f"{len(close_runners_up)} weitere/r GND-Kandidat(en) mit ähnlichem Namen "
            f"(vermutlich Dubletten oder nicht unterscheidbar): "
            + ", ".join(f"{s['c'].get('preferredName')} ({s['c'].get('id')})" for s in close_runners_up),
        )

    if tier == 2:
        return _build("unsicher", "Nur über Namenssuche ohne GND-Berufskennzeichnung 'Orgelbauer' gefunden")

    if best["dates_ok"] is None and (person["lebensdaten"]["geburtsjahr"] or person["lebensdaten"]["todesjahr"]):
        return _build("unsicher", "Lebensdaten in Quelle vorhanden, aber bei GND-Kandidat nicht vergleichbar")

    return _build("ok", None)


def run(builders_path: Path, cache_path: Path, refresh: bool) -> None:
    lemmata = json.loads(builders_path.read_text(encoding="utf-8"))
    results: dict[str, GndMatch] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    todo = [
        (lemma, person)
        for lemma in lemmata
        for person in lemma["personen"]
        if refresh or f"{lemma['id']}-{person['index']}" not in results
    ]
    total_persons = sum(len(lemma["personen"]) for lemma in lemmata)
    print(f"{total_persons} Personen insgesamt, {len(results)} bereits im Cache, {len(todo)} werden abgefragt.")

    for done, (lemma, person) in enumerate(todo, start=1):
        key = f"{lemma['id']}-{person['index']}"
        try:
            results[key] = match_person(person)
        except requests.RequestException as exc:
            print(f"[{done}/{len(todo)}] {key}: Netzwerkfehler, wird im naechsten Lauf erneut versucht ({exc})")
            continue
        if done % 50 == 0:
            print(f"[{done}/{len(todo)}] ...")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter

    counts = Counter(r["status"] for r in results.values())
    print(f"Fertig. {dict(counts)} (von {total_persons} Personen).")


if __name__ == "__main__":
    import argparse

    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Match builder persons against GND via lobid")
    parser.add_argument("--builders", default=str(repo_root / "site" / "src" / "data" / "builders.json"))
    parser.add_argument("--cache", default=str(repo_root / "etl" / "cache" / "gnd_matches.json"))
    parser.add_argument("--refresh", action="store_true", help="auch bereits gecachte Personen neu abfragen")
    args = parser.parse_args()
    run(Path(args.builders), Path(args.cache), args.refresh)
