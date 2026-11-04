"""Batch-geocode distinct organ locations via Nominatim (OpenStreetMap).

Run standalone, locally, once (then re-run occasionally for new places -
already-cached place_keys are never re-queried):

    cd etl/src
    <venv>/Scripts/python.exe geocode/geocode.py --site-data ../../site/src/data

Respects Nominatim's usage policy: max 1 request/second, identifying
User-Agent, structured query params. A full first run over ~8,800 distinct
places takes roughly 2.5-3 hours - that's expected, not a hang. The cache
is written to disk every 25 requests so an interrupted run loses at most
a couple of minutes of progress, not the whole thing.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "orgeldatenbank-bayern-geocoder/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
REQUEST_INTERVAL_SECONDS = 1.1
SAVE_EVERY = 25


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_places(organs_dir: Path) -> dict[str, dict]:
    """place_key -> representative {ort, plz, gemeinde, landkreis}."""
    places: dict[str, dict] = {}
    for shard_path in sorted(organs_dir.glob("*.json")):
        organs = json.loads(shard_path.read_text(encoding="utf-8"))
        for organ in organs:
            key = organ.get("place_key")
            if key and key not in places:
                places[key] = {
                    "ort": organ.get("ort"),
                    "plz": organ["adresse"].get("plz"),
                    "gemeinde": organ.get("gemeinde"),
                    "landkreis": organ.get("landkreis"),
                }
    return places


def query_nominatim(params: dict) -> dict | None:
    response = requests.get(
        NOMINATIM_URL,
        params={**params, "format": "jsonv2", "limit": 1, "country": "Germany"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    results = response.json()
    return results[0] if results else None


def geocode_place(place: dict) -> dict:
    ort = place.get("ort")
    plz = place.get("plz")
    gemeinde = place.get("gemeinde")
    landkreis = place.get("landkreis")

    if not ort:
        return {"status": "not_found", "reason": "kein Ortsname"}

    try:
        result = None
        if plz:
            result = query_nominatim({"postalcode": plz, "city": ort})
        if result is None:
            # Fallback: city name alone, optionally qualified by Gemeinde/Landkreis
            query_city = ort if not gemeinde or gemeinde == ort else f"{ort}, {gemeinde}"
            time.sleep(REQUEST_INTERVAL_SECONDS)
            result = query_nominatim({"city": query_city})
        if result is None and landkreis:
            time.sleep(REQUEST_INTERVAL_SECONDS)
            result = query_nominatim({"city": ort, "county": landkreis})

        if result is None:
            return {"status": "not_found"}
        return {
            "status": "ok",
            "lat": float(result["lat"]),
            "lon": float(result["lon"]),
            "display_name": result.get("display_name"),
        }
    except requests.RequestException as exc:
        return {"status": "error", "reason": str(exc)}


def run(site_data_dir: Path, cache_dir: Path, refresh: bool) -> None:
    organs_dir = site_data_dir / "organs"
    cache_path = cache_dir / "geocode_cache.json"
    overrides_path = cache_dir / "geocode_overrides.json"

    places = collect_places(organs_dir)
    cache = load_json(cache_path, {})
    overrides = load_json(overrides_path, {})
    print(f"{len(places)} distinkte Orte gefunden, {len(cache)} bereits im Cache.")

    todo = [key for key in places if refresh or key not in cache or cache[key].get("status") == "error"]
    print(f"{len(todo)} Orte werden abgefragt (Rest kommt aus dem Cache).")

    for i, key in enumerate(todo, start=1):
        if key in overrides:
            continue
        result = geocode_place(places[key])
        result["fetched_at"] = time.strftime("%Y-%m-%d")
        cache[key] = result
        status_label = result["status"]
        print(f"[{i}/{len(todo)}] {key} -> {status_label}")

        if i % SAVE_EVERY == 0:
            save_json(cache_path, cache)
        time.sleep(REQUEST_INTERVAL_SECONDS)

    save_json(cache_path, cache)
    ok = sum(1 for v in cache.values() if v.get("status") == "ok")
    not_found = sum(1 for v in cache.values() if v.get("status") == "not_found")
    errors = sum(1 for v in cache.values() if v.get("status") == "error")
    print(f"Fertig. ok={ok} not_found={not_found} error={errors} (von {len(places)} Orten).")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Geocode distinct organ locations via Nominatim")
    parser.add_argument("--site-data", default=str(repo_root / "site" / "src" / "data"))
    parser.add_argument("--cache-dir", default=str(repo_root / "etl" / "cache"))
    parser.add_argument("--refresh", action="store_true", help="auch bereits gecachte Orte neu abfragen")
    args = parser.parse_args()
    run(Path(args.site_data), Path(args.cache_dir), args.refresh)


if __name__ == "__main__":
    main()
