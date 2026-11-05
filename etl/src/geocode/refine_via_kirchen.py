"""Refine place coordinates using Wikidata positions of GND-matched churches.

Run after match/gnd_match_kirchen.py (and ideally match/apply_gnd_kirchen.py):

    cd etl/src
    <venv>/Scripts/python.exe geocode/refine_via_kirchen.py

Every GND "BuildingOrMemorial" record that also exists as a Wikidata item
usually carries a precise, surveyed coordinate (property P625) - and
Wikidata cross-references GND via property P227, so a church we already
matched to a GND id (see match/gnd_match_kirchen.py) can often be looked
up for an exact building-level position, not just a village-level
estimate. That is strictly better than any of this project's other
coordinate sources (Nominatim's or AX_Ortslage's village centroid), so
where available it overrides the place's coordinate outright.

Queried in batches via Wikidata's SPARQL endpoint (a VALUES clause with
many GND ids per request) rather than one request per church - friendlier
to the shared public endpoint and far faster for ~ a few thousand ids.

A place with more than one GND-matched church (rare but possible) gets
the average of their Wikidata positions - they are, by construction,
within the same village, so this stays accurate at map-pin scale.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "orgeldatenbank-bayern-geocoder/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
BATCH_SIZE = 150
_POINT = re.compile(r"Point\(([-\d.]+)\s+([-\d.]+)\)")


def _fetch_coords(gnd_ids: list[str]) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    for i in range(0, len(gnd_ids), BATCH_SIZE):
        batch = gnd_ids[i : i + BATCH_SIZE]
        values = " ".join(f'"{g}"' for g in batch)
        query = f"""
            SELECT ?gnd ?coord WHERE {{
              VALUES ?gnd {{ {values} }}
              ?item wdt:P227 ?gnd .
              ?item wdt:P625 ?coord .
            }}
        """
        response = requests.get(
            SPARQL_URL, params={"query": query, "format": "json"},
            headers={"User-Agent": USER_AGENT}, timeout=60,
        )
        response.raise_for_status()
        for binding in response.json()["results"]["bindings"]:
            m = _POINT.match(binding["coord"]["value"])
            if m:
                lon, lat = float(m.group(1)), float(m.group(2))
                coords[binding["gnd"]["value"]] = (lat, lon)
        print(f"[{min(i + BATCH_SIZE, len(gnd_ids))}/{len(gnd_ids)}] ... ({len(coords)} Koordinaten bisher)")
        time.sleep(1)
    return coords


def run(site_data_dir: Path, cache_dir: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from geocode.geocode import collect_places  # noqa: E402

    places = collect_places(site_data_dir / "organs")
    cache = json.loads((cache_dir / "geocode_cache.json").read_text(encoding="utf-8"))
    kirchen_matches = json.loads((cache_dir / "gnd_kirchen_matches.json").read_text(encoding="utf-8"))

    place_to_gnd_ids: dict[str, set[str]] = defaultdict(set)
    for key, match in kirchen_matches.items():
        if match.get("status") != "ok" or not match.get("gnd_id"):
            continue
        place_key = key.split("::", 1)[0]
        place_to_gnd_ids[place_key].add(match["gnd_id"])

    all_gnd_ids = sorted({gnd for ids in place_to_gnd_ids.values() for gnd in ids})
    print(f"{len(all_gnd_ids)} GND-Kirchen-IDs werden gegen Wikidata abgefragt ...")
    wikidata_coords = _fetch_coords(all_gnd_ids)
    print(f"{len(wikidata_coords)} Kirchen haben eine Wikidata-Koordinate.")

    refined = 0
    for place_key, gnd_ids in place_to_gnd_ids.items():
        points = [wikidata_coords[g] for g in gnd_ids if g in wikidata_coords]
        if not points:
            continue
        lat = sum(p[0] for p in points) / len(points)
        lon = sum(p[1] for p in points) / len(points)
        place = places.get(place_key, {})
        cache[place_key] = {
            "status": "ok",
            "lat": lat,
            "lon": lon,
            "display_name": f"{place.get('ort')} (Wikidata, ueber GND-Kirchenzuordnung)",
            "quelle": "wikidata_via_gnd_kirche",
            "fetched_at": time.strftime("%Y-%m-%d"),
        }
        refined += 1

    (cache_dir / "geocode_cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{refined} Orte auf Gebaeude-genaue Wikidata-Koordinaten praezisiert.")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data", repo_root / "etl" / "cache")
