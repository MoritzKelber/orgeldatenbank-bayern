"""Match organ-hosting churches against the GND via lobid.org.

Run after the organ data has been built:

    cd etl/src
    <venv>/Scripts/python.exe match/gnd_match_kirchen.py

The GND catalogs many named church buildings under the entity type
"BuildingOrMemorial", conventionally as "<Widmungsname> (<Ort>)" - e.g.
"Sankt Laurentius (Marktheidenfeld)" (see
https://explore.gnd.network/gnd/4104564-6 for the Munich Frauenkirche).
For each distinct (Kirche, Ort) pair in the organ data, this queries
lobid for a BuildingOrMemorial in Bavaria whose name contains both the
church's dedication (its most distinctive word, e.g. "Laurentius" from
"St. Laurentius") and the place name - exact enough in practice that
getting exactly one hit is already strong evidence, since two different
churches sharing both a saint's name AND a village are effectively never
both GND-catalogued.

Institutional entries that aren't really named churches (e.g.
"Hausorgel", "Kreiskrankenhaus", "Volkshochschule") naturally have no
usable dedication word and are skipped as "nicht_zutreffend" rather than
queried - not a gap, just not applicable.

GND coverage of parish/filial churches is well short of universal (many
small village churches have no authority record at all), so a sizeable
"keine" rate is expected, not a bug.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import TypedDict

import requests

LOBID_URL = "https://lobid.org/gnd/search"
USER_AGENT = "orgeldatenbank-bayern-gnd-matcher/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
REQUEST_INTERVAL_SECONDS = 0.35

_STOPWORDS = {
    "sankt", "st", "heilige", "heiliger", "heiligen", "kirche", "kapelle",
    "pfarrkirche", "filialkirche", "wallfahrtskirche", "klosterkirche",
    "schlosskapelle", "schulkapelle", "und", "der", "die", "das", "ehem",
    "zur", "zum", "alt", "alte", "alter", "hl",
}


class KircheGndMatch(TypedDict):
    status: str  # "ok" | "unsicher" | "keine" | "nicht_zutreffend"
    gnd_id: str | None
    url: str | None
    preferred_name: str | None
    candidates_considered: int
    grund: str | None


def core_tokens(kirche: str) -> list[str]:
    text = kirche.split("(")[0]
    text = re.sub(r"[^a-zA-ZäöüÄÖÜß]+", " ", text)
    return [t.lower() for t in text.split() if len(t) >= 4 and t.lower() not in _STOPWORDS]


def _query(token: str, place: str, attempt: int = 1) -> list[dict]:
    q = f'type:BuildingOrMemorial AND geographicAreaCode.label:Bayern AND preferredName:*{token}* AND preferredName:*{place}*'
    try:
        response = requests.get(
            LOBID_URL, params={"q": q, "format": "json", "size": 20},
            headers={"User-Agent": USER_AGENT}, timeout=15,
        )
        response.raise_for_status()
        return response.json().get("member", [])
    except requests.RequestException:
        if attempt >= 4:
            raise
        time.sleep(2**attempt)
        return _query(token, place, attempt + 1)


def match_kirche(kirche: str, ort: str | None, gemeinde: str | None) -> KircheGndMatch:
    tokens = core_tokens(kirche)
    if not tokens or not ort:
        return {
            "status": "nicht_zutreffend", "gnd_id": None, "url": None,
            "preferred_name": None, "candidates_considered": 0,
            "grund": "kein nutzbarer Widmungsname (z.B. Institutionsname statt Kirchenname)",
        }

    places = [ort] if not gemeinde or gemeinde == ort else [ort, gemeinde]
    for i, place in enumerate(places):
        candidates = _query(tokens[0], place)
        if i < len(places) - 1:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        if candidates:
            break
    else:
        return {
            "status": "keine", "gnd_id": None, "url": None,
            "preferred_name": None, "candidates_considered": 0, "grund": None,
        }

    if len(candidates) == 1:
        c = candidates[0]
        return {
            "status": "ok", "gnd_id": c.get("gndIdentifier"), "url": c.get("id"),
            "preferred_name": c.get("preferredName"), "candidates_considered": 1, "grund": None,
        }

    c = candidates[0]
    others = ", ".join(f"{m.get('preferredName')} ({m.get('id')})" for m in candidates[1:4])
    return {
        "status": "unsicher", "gnd_id": c.get("gndIdentifier"), "url": c.get("id"),
        "preferred_name": c.get("preferredName"), "candidates_considered": len(candidates),
        "grund": f"{len(candidates)} Kandidaten gefunden, u.a.: {others}",
    }


def _collect_pairs(organs_dir: Path) -> dict[str, dict]:
    """key -> {kirche, ort, gemeinde} for every distinct (place_key, Kirche)."""
    pairs: dict[str, dict] = {}
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            kirche = (organ.get("kirche") or "").strip()
            place_key = organ.get("place_key")
            if not kirche or not place_key:
                continue
            key = f"{place_key}::{kirche}"
            if key not in pairs:
                pairs[key] = {"kirche": kirche, "ort": organ.get("ort"), "gemeinde": organ.get("gemeinde")}
    return pairs


def run(site_data_dir: Path, cache_path: Path, refresh: bool) -> None:
    pairs = _collect_pairs(site_data_dir / "organs")
    results: dict[str, KircheGndMatch] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    todo = [key for key in pairs if refresh or key not in results]
    print(f"{len(pairs)} Kirchen insgesamt, {len(results) - len([k for k in results if k not in pairs])} bereits im Cache, {len(todo)} werden abgefragt.")

    for done, key in enumerate(todo, start=1):
        p = pairs[key]
        try:
            results[key] = match_kirche(p["kirche"], p["ort"], p["gemeinde"])
        except requests.RequestException as exc:
            print(f"[{done}/{len(todo)}] {key}: Netzwerkfehler, wird im naechsten Lauf erneut versucht ({exc})")
            continue
        if done % 50 == 0:
            print(f"[{done}/{len(todo)}] ...")
            cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    counts = Counter(r["status"] for r in results.values())
    print(f"Fertig. {dict(counts)} (von {len(pairs)} Kirchen).")


if __name__ == "__main__":
    import argparse

    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Match organ-hosting churches against GND via lobid")
    parser.add_argument("--site-data", default=str(repo_root / "site" / "src" / "data"))
    parser.add_argument("--cache", default=str(repo_root / "etl" / "cache" / "gnd_kirchen_matches.json"))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    run(Path(args.site_data), Path(args.cache), args.refresh)
