"""Geocode one representative coordinate per Landkreis (or kreisfreie Stadt).

Run once (then only to pick up newly-appearing Landkreis/Stadt names):

    cd etl/src
    <venv>/Scripts/python.exe geocode/fetch_landkreis_koordinaten.py

This is the third, coarsest of the three geographic levels the site
distinguishes: Kirche (building, see refine_via_kirchen.py) -> Ort
(village, see geocode.py) -> Landkreis (county). Bydaten.LKR is a
normdata label, not itself geocoded, and for every kreisfreie Stadt it
is literally the placeholder "krfr. Stadt" rather than naming the city
(see crosscheck_ortslage.py's comment on the same quirk) - so the
*effective* name geocoded here is the Landkreis name, or for a kreisfreie
Stadt, its Gemeinde name instead.

Only ~88 distinct names in all of Bavaria, so a plain Nominatim search
per name (politely paced) is simplest - no need for the batching tricks
used for the much larger Ortslage/church datasets.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from geocode.geocode import NOMINATIM_URL, REQUEST_INTERVAL_SECONDS, USER_AGENT  # noqa: E402


def effective_landkreis_name(organ: dict) -> str | None:
    landkreis = organ.get("landkreis")
    if landkreis == "krfr. Stadt":
        return organ.get("gemeinde")
    return landkreis


def collect_names(organs_dir: Path) -> set[str]:
    names: set[str] = set()
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            name = effective_landkreis_name(organ)
            if name:
                names.add(name)
    return names


def query(name: str, is_kreisfreie_stadt: bool) -> dict | None:
    q = f"{name}, Bayern" if is_kreisfreie_stadt else f"Landkreis {name}, Bayern"
    response = requests.get(
        NOMINATIM_URL, params={"q": q, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": USER_AGENT}, timeout=20,
    )
    response.raise_for_status()
    results = response.json()
    return results[0] if results else None


def run(site_data_dir: Path, cache_path: Path) -> None:
    organs_dir = site_data_dir / "organs"
    kreisfreie: set[str] = set()
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            if organ.get("landkreis") == "krfr. Stadt" and organ.get("gemeinde"):
                kreisfreie.add(organ["gemeinde"])

    names = collect_names(organs_dir)
    cache: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = [n for n in sorted(names) if n not in cache]
    print(f"{len(names)} Landkreise/kreisfreie Staedte, {len(cache)} bereits im Cache, {len(todo)} werden abgefragt.")

    for i, name in enumerate(todo, start=1):
        result = query(name, name in kreisfreie)
        if result:
            cache[name] = {
                "lat": float(result["lat"]), "lon": float(result["lon"]),
                "ist_kreisfreie_stadt": name in kreisfreie,
                "display_name": result.get("display_name"),
            }
            print(f"[{i}/{len(todo)}] {name} -> ok")
        else:
            print(f"[{i}/{len(todo)}] {name} -> kein Treffer")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fertig. {len(cache)} von {len(names)} Landkreisen/Staedten mit Koordinate.")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data", repo_root / "etl" / "cache" / "landkreis_koordinaten.json")
