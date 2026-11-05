"""Resolve remaining doubtful places by geocoding the church itself, by name.

Run after geocode.py and crosscheck_ortslage.py:

    cd etl/src
    <venv>/Scripts/python.exe geocode/geocode_by_kirche.py

Every organ record names the specific church it stands in (e.g. "St.
Laurentius"), which Nominatim can search for directly as a named
place-of-worship POI - a much more specific, less ambiguous query than
the bare village name alone (several Bavarian villages share a name;
hardly any share both a village name AND the exact same church name in
the same Landkreis). This targets exactly the two groups that are still
doubtful after the Ortslage cross-check:

- status "not_found" (no match at all, even in AX_Ortslage).
- entries crosscheck_ortslage.py flagged as a 5-50km "moderate" gap
  between the Nominatim village match and the nearest AX_Ortslage
  candidate - this query independently settles which (if either) was
  right.

A successful church-name hit is treated as more authoritative than a
village-level match (it pinpoints the actual building) and overrides
both, tagged "quelle": "nominatim_kirche". Not run against every place
indiscriminately - that would be ~8,800 extra requests for cases that
are already fine; it only touches places this run's two groups cover
(typically a few hundred).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from geocode.geocode import NOMINATIM_URL, REQUEST_INTERVAL_SECONDS, USER_AGENT, collect_places  # noqa: E402

BBOX = {"lat_min": 47.2, "lat_max": 50.7, "lon_min": 8.9, "lon_max": 13.9}


def _in_bavaria(lat: float, lon: float) -> bool:
    return BBOX["lat_min"] <= lat <= BBOX["lat_max"] and BBOX["lon_min"] <= lon <= BBOX["lon_max"]


def _collect_kirchen(organs_dir: Path) -> dict[str, str]:
    """place_key -> a representative Kirche name (first non-empty one seen)."""
    result: dict[str, str] = {}
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            key = organ.get("place_key")
            kirche = (organ.get("kirche") or "").strip()
            if key and kirche and key not in result:
                result[key] = kirche
    return result


def _query(kirche: str, ort: str, gemeinde: str | None) -> dict | None:
    ort_context = f"{ort}, {gemeinde}" if gemeinde and gemeinde != ort else ort
    response = requests.get(
        NOMINATIM_URL,
        params={"q": f"{kirche}, {ort_context}, Bayern", "format": "jsonv2", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    results = response.json()
    return results[0] if results else None


def run(site_data_dir: Path, cache_dir: Path) -> None:
    cache = json.loads((cache_dir / "geocode_cache.json").read_text(encoding="utf-8"))
    review = json.loads((cache_dir / "ortslage_distance_review.json").read_text(encoding="utf-8"))
    kirchen = _collect_kirchen(site_data_dir / "organs")

    targets = sorted(
        key
        for key in set(cache) | set(review)
        if key in kirchen and (cache.get(key, {}).get("status") == "not_found" or key in review)
    )
    print(f"{len(targets)} Orte werden ueber den Kirchennamen erneut abgefragt.")
    places = collect_places(site_data_dir / "organs")

    resolved_not_found = 0
    resolved_review = 0
    unresolved = 0

    for i, key in enumerate(targets, start=1):
        place = places.get(key, {})
        try:
            result = _query(kirchen[key], place.get("ort") or "", place.get("gemeinde"))
        except requests.RequestException as exc:
            print(f"[{i}/{len(targets)}] {key}: Netzwerkfehler ({exc}), uebersprungen")
            time.sleep(REQUEST_INTERVAL_SECONDS)
            continue

        was_not_found = cache.get(key, {}).get("status") == "not_found"
        if result and _in_bavaria(float(result["lat"]), float(result["lon"])):
            cache[key] = {
                "status": "ok",
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "display_name": result.get("display_name"),
                "quelle": "nominatim_kirche",
                "fetched_at": time.strftime("%Y-%m-%d"),
            }
            review.pop(key, None)
            if was_not_found:
                resolved_not_found += 1
            else:
                resolved_review += 1
        else:
            unresolved += 1

        if i % 25 == 0:
            print(f"[{i}/{len(targets)}] ...")
            (cache_dir / "geocode_cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    (cache_dir / "geocode_cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    (cache_dir / "ortslage_distance_review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Vorher nicht gefunden, jetzt per Kirchenname geloest: {resolved_not_found}")
    print(f"Vorher moderate Abweichung, jetzt per Kirchenname geklaert: {resolved_review}")
    print(f"Weiterhin ungeloest: {unresolved}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data", repo_root / "etl" / "cache")
