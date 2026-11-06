"""Fetch the Katholisches Buero Bayern's Pfarramt (parish office) point layer.

Run once (then only to refresh):

    cd etl/src
    <venv>/Scripts/python.exe geocode/fetch_pfarramt.py

A fourth geodata source, found via the GDI-Bayern/Geoportal Bayern CSW
catalog ("Katholische Kirche in Bayern" dataset): an ArcGIS Server run by
the Katholisches Buero Bayern (the dioceses' joint office), whose
"Pfarramt" layer geocodes every Catholic parish office by street address
- per its own metadata, aiming for house-number precision. The office is
usually at or immediately next to the parish's main church, so this
fills in building-level-ish precision for many Catholic parishes that
have no Wikidata/GND entry (gnd_match_kirchen.py only found ~1,600 of
them). Catholic-only - doesn't help Protestant/Evangelical churches.

Source: https://kbb.alta4cloud.com/arcgis/rest/services/KBB/VA_KATH/MapServer/0
Output: etl/cache/kbb_pfarramt_raw.json, a list of attribute dicts with
lat/lon added (already reprojected to WGS84 via outSR=4326).
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

QUERY_URL = "https://kbb.alta4cloud.com/arcgis/rest/services/KBB/VA_KATH/MapServer/0/query"
USER_AGENT = "orgeldatenbank-bayern-geocoder/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
PAGE_SIZE = 1000


def run(out_path: Path) -> None:
    all_records: list[dict] = []
    offset = 0
    while True:
        response = requests.get(
            QUERY_URL,
            params={
                "where": "1=1", "outFields": "*", "returnGeometry": "true",
                "outSR": "4326", "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
                "f": "json",
            },
            headers={"User-Agent": USER_AGENT}, timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        if not features:
            break
        for f in features:
            attrs = f["attributes"]
            geom = f.get("geometry")
            if geom:
                attrs["lat"] = geom["y"]
                attrs["lon"] = geom["x"]
                all_records.append(attrs)
        print(f"{len(all_records)} Datensaetze geladen ...")
        offset += PAGE_SIZE
        if not data.get("exceededTransferLimit") and len(features) < PAGE_SIZE:
            break

    out_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fertig. {len(all_records)} Pfarraemter -> {out_path}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "etl" / "cache" / "kbb_pfarramt_raw.json")
