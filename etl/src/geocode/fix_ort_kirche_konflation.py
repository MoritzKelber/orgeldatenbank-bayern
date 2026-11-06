"""Re-geocode Ort-level places that were wrongly set to a specific church's position.

Run once, to clean up a modelling mistake:

    cd etl/src
    <venv>/Scripts/python.exe geocode/fix_ort_kirche_konflation.py

refine_via_kirchen.py and geocode_by_kirche.py both, at different points,
wrote a *church's* coordinate into geocode_cache.json - the Ort-level
dataset. That conflates two of the three geographic layers the site now
distinguishes (see build_kirchen_layer.py's module docstring): a place
like "München, 81541" ended up tagged with one specific parish's exact
position, with every other organ at that postcode implicitly (and
wrongly) pulled along with it, instead of a genuine area-level estimate.
It matters most in cities, where a postcode covers a whole Stadtteil,
not something as small as one church's footyard - a single church's
point is not a fair stand-in for the postcode area as a whole.

This finds every place_key still tagged "wikidata_via_gnd_kirche" or
"nominatim_kirche" and re-geocodes it the same way as every other place -
by Ort/PLZ/Gemeinde/Landkreis alone (geocode.py's geocode_place, no
church name involved) - so the Ort layer goes back to representing the
place, not a building inside it. The Kirche layer (kirchen.json) already
holds the precise church positions separately and is unaffected.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from geocode.geocode import REQUEST_INTERVAL_SECONDS, collect_places, geocode_place  # noqa: E402

TAINTED_SOURCES = ("wikidata_via_gnd_kirche", "nominatim_kirche")


def run(site_data_dir: Path, cache_dir: Path) -> None:
    cache_path = cache_dir / "geocode_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    places = collect_places(site_data_dir / "organs")

    tainted = [key for key, geo in cache.items() if geo.get("quelle") in TAINTED_SOURCES]
    print(f"{len(tainted)} Orte waren auf eine einzelne Kirchen-Position statt eine Orts-Position gesetzt.")

    for i, key in enumerate(tainted, start=1):
        place = places.get(key)
        if not place:
            continue
        result = geocode_place(place)
        result["fetched_at"] = time.strftime("%Y-%m-%d")
        cache[key] = result
        if i % 25 == 0:
            print(f"[{i}/{len(tainted)}] ...")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter

    print(f"Fertig. Neue Status-Verteilung der betroffenen Orte: {Counter(cache[k]['status'] for k in tainted)}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data", repo_root / "etl" / "cache")
