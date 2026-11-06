"""Build site/public/data/landkreise.json - the coarsest map layer.

Run after fetch_landkreis_koordinaten.py:

    cd etl/src
    <venv>/Scripts/python.exe geocode/build_landkreise_layer.py

Groups every organ by its effective Landkreis/kreisfreie-Stadt name (see
fetch_landkreis_koordinaten.py) and attaches that unit's coordinate. This
layer covers every organ in the database, including the ~600 that have
no Ort-level coordinate at all - at Landkreis precision, nothing is
left off the map.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from geocode.fetch_landkreis_koordinaten import effective_landkreis_name  # noqa: E402


def run(site_data_dir: Path, cache_dir: Path, public_data_dir: Path) -> None:
    import json

    organs_dir = site_data_dir / "organs"
    coords = json.loads((cache_dir / "landkreis_koordinaten.json").read_text(encoding="utf-8"))

    counts: dict[str, int] = defaultdict(int)
    orte: dict[str, set[str]] = defaultdict(set)
    organs_ohne_landkreis = 0
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            name = effective_landkreis_name(organ)
            if not name:
                organs_ohne_landkreis += 1
                continue
            counts[name] += 1
            if organ.get("ort"):
                orte[name].add(organ["ort"])

    landkreise = []
    for name, geo in coords.items():
        landkreise.append(
            {
                "name": name,
                "ist_kreisfreie_stadt": geo.get("ist_kreisfreie_stadt", False),
                "lat": geo["lat"],
                "lon": geo["lon"],
                "anzahl_orgeln": counts.get(name, 0),
                "anzahl_orte": len(orte.get(name, set())),
            }
        )

    print(f"{len(landkreise)} Landkreise/kreisfreie Staedte, {organs_ohne_landkreis} Orgeln ohne Landkreis-Angabe.")
    public_data_dir.mkdir(parents=True, exist_ok=True)
    (public_data_dir / "landkreise.json").write_text(
        json.dumps({"landkreise": landkreise}, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data",
        repo_root / "etl" / "cache",
        repo_root / "site" / "public" / "data",
    )
