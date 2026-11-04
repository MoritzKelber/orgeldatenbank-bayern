"""Build site/public/data/places.json from the geocode cache + organ data.

Run after geocode.py has (fully or partially) populated the cache:

    cd etl/src
    <venv>/Scripts/python.exe geocode/build_places.py

Produces one entry per successfully-geocoded place_key, each carrying
the ids of every organ at that place (the map clusters at place level,
not per-organ - see the plan). Un-geocodable places are simply left out;
the map page reports how many organs that affects.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src, for `transform`
from transform.jahr import format_jahr  # noqa: E402


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def run(site_data_dir: Path, public_data_dir: Path, cache_dir: Path) -> None:
    organs_dir = site_data_dir / "organs"
    cache = load_json(cache_dir / "geocode_cache.json", {})
    overrides = load_json(cache_dir / "geocode_overrides.json", {})
    geocoded = {**cache, **overrides}

    organs_by_place: dict[str, list[dict]] = defaultdict(list)
    place_info: dict[str, dict] = {}
    total_organs = 0
    organs_without_place_key = 0
    for shard_path in sorted(organs_dir.glob("*.json")):
        organs = json.loads(shard_path.read_text(encoding="utf-8"))
        total_organs += len(organs)
        for organ in organs:
            key = organ.get("place_key")
            if not key:
                organs_without_place_key += 1
                continue
            organs_by_place[key].append(
                {"id": organ["id"], "kirche": organ.get("kirche"), "jahr_anzeige": format_jahr(organ["jahr"])}
            )
            if key not in place_info:
                place_info[key] = {"ort": organ.get("ort"), "landkreis": organ.get("landkreis")}

    places = []
    organs_not_geocoded = 0
    for key, place_organs in organs_by_place.items():
        geo = geocoded.get(key)
        if not geo or geo.get("status") != "ok":
            organs_not_geocoded += len(place_organs)
            continue
        places.append(
            {
                "place_key": key,
                "lat": geo["lat"],
                "lon": geo["lon"],
                "ort": place_info[key]["ort"],
                "landkreis": place_info[key]["landkreis"],
                "organs": place_organs,
            }
        )

    organs_ohne_koordinate = organs_not_geocoded + organs_without_place_key
    print(f"{len(places)} geokodierte Orte von {len(organs_by_place)} distinkten Orten.")
    print(f"{organs_ohne_koordinate} von {total_organs} Orgeln ohne Koordinate (Ort nicht geokodiert oder kein Ort erfasst).")

    public_data_dir.mkdir(parents=True, exist_ok=True)
    (public_data_dir / "places.json").write_text(
        json.dumps({"places": places, "organs_ohne_koordinate": organs_ohne_koordinate}, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Build places.json for the map from the geocode cache")
    parser.add_argument("--site-data", default=str(repo_root / "site" / "src" / "data"))
    parser.add_argument("--public-data", default=str(repo_root / "site" / "public" / "data"))
    parser.add_argument("--cache-dir", default=str(repo_root / "etl" / "cache"))
    args = parser.parse_args()
    run(Path(args.site_data), Path(args.public_data), Path(args.cache_dir))


if __name__ == "__main__":
    main()
