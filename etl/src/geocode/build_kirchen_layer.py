"""Build site/public/data/kirchen.json - the building-precise map layer.

Run after match/gnd_match_kirchen.py and fetch_pfarramt.py:

    cd etl/src
    <venv>/Scripts/python.exe geocode/build_kirchen_layer.py

One of the three geographic layers the map distinguishes: Kirche
(building, this file) -> Ort (village, places.json) -> Landkreis
(county, landkreise.json). Unlike refine_via_kirchen.py, this never
writes into geocode_cache.json - the Ort-level place coordinate and the
Kirche-level building coordinate are kept as separate datasets on
purpose, each shown as its own map layer, not collapsed into one.

Two independent sources, tried in order of precision:

1. Wikidata (property P625) for whichever matched church
   (gnd_match_kirchen.py, status "ok") also has a Wikidata item linked
   via P227 - the exact, surveyed building position.
2. The Katholisches Buero Bayern's "Pfarramt" layer (fetch_pfarramt.py) -
   every Catholic parish office's street address, which per its own
   metadata aims for house-number precision and is usually at or next to
   the parish's main church. Matched by splitting its "Ort-Widmung"
   naming (e.g. "Deiningen-St. Martin") and comparing both parts against
   our own Ort/Kirche fields - Catholic-only, and only used for churches
   tier 1 didn't already resolve.

Each output entry keeps which tier it came from (`quelle`), so the map
and detail pages can show that distinction rather than hide it.
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from geocode.crosscheck_ortslage import _norm  # noqa: E402
from match.gnd_match_kirchen import core_tokens  # noqa: E402


def _fetch_wikidata_coords(gnd_ids: list[str]) -> dict[str, tuple[float, float]]:
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


def _build_pfarramt_index(records: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """(norm_ort, core_token) -> matching Pfarramt records."""
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in records:
        name = (rec.get("Pf_Name") or "").strip()
        parts = re.split(r"\s*-\s*|\s{2,}", name, maxsplit=1)
        if len(parts) != 2:
            continue
        ort_part, widmung_part = parts
        norm_ort = _norm(ort_part)
        for token in core_tokens(widmung_part):
            index[(norm_ort, token)].append(rec)
    return index


_TYP_PRIORITY = {"Hauptstelle": 0, "Sitz": 1, None: 2, "Nebenstelle": 3}


def _best_pfarramt_match(records: list[dict]) -> dict:
    return min(records, key=lambda r: _TYP_PRIORITY.get(r.get("PA_Typ_lang"), 2))


def run(site_data_dir: Path, cache_dir: Path, public_data_dir: Path) -> None:
    organs_dir = site_data_dir / "organs"
    kirchen_matches = json.loads((cache_dir / "gnd_kirchen_matches.json").read_text(encoding="utf-8"))

    gnd_ids = sorted({m["gnd_id"] for m in kirchen_matches.values() if m.get("status") == "ok" and m.get("gnd_id")})
    print(f"{len(gnd_ids)} GND-Kirchen-IDs werden gegen Wikidata abgefragt ...")
    wikidata_coords = _fetch_wikidata_coords(gnd_ids)
    print(f"{len(wikidata_coords)} Kirchen haben eine Wikidata-Koordinate.")

    pfarramt_path = cache_dir / "kbb_pfarramt_raw.json"
    pfarramt_index = _build_pfarramt_index(json.loads(pfarramt_path.read_text(encoding="utf-8"))) if pfarramt_path.exists() else {}

    organs_by_key: dict[str, list[dict]] = defaultdict(list)
    kirche_info: dict[str, dict] = {}
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            kirche = (organ.get("kirche") or "").strip()
            place_key = organ.get("place_key")
            if not kirche or not place_key:
                continue
            key = f"{place_key}::{kirche}"

            coord: tuple[float, float] | None = None
            quelle = None
            gnd_url = None
            match = kirchen_matches.get(key)
            if match and match.get("status") == "ok":
                coord = wikidata_coords.get(match.get("gnd_id"))
                if coord:
                    quelle = "wikidata_via_gnd_kirche"
                    gnd_url = match.get("url")

            if coord is None and pfarramt_index:
                norm_ort = _norm(organ.get("ort") or "")
                candidates: list[dict] = []
                for token in core_tokens(kirche):
                    candidates.extend(pfarramt_index.get((norm_ort, token), []))
                if candidates:
                    best = _best_pfarramt_match(candidates)
                    coord = (best["lat"], best["lon"])
                    quelle = "kbb_pfarramt"

            if coord is None:
                continue

            organs_by_key[key].append({"id": organ["id"]})
            if key not in kirche_info:
                kirche_info[key] = {
                    "kirche": kirche, "ort": organ.get("ort"), "landkreis": organ.get("landkreis"),
                    "lat": coord[0], "lon": coord[1], "quelle": quelle, "gnd_url": gnd_url,
                }

    from transform.jahr import format_jahr  # noqa: E402

    jahr_by_id: dict[int, str | None] = {}
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            jahr_by_id[organ["id"]] = format_jahr(organ["jahr"])

    kirchen = []
    for key, info in kirche_info.items():
        kirchen.append(
            {
                "key": key,
                "lat": info["lat"],
                "lon": info["lon"],
                "kirche": info["kirche"],
                "ort": info["ort"],
                "landkreis": info["landkreis"],
                "quelle": info["quelle"],
                "gnd_url": info["gnd_url"],
                "organs": [{"id": o["id"], "jahr_anzeige": jahr_by_id.get(o["id"])} for o in organs_by_key[key]],
            }
        )

    via_wikidata = sum(1 for k in kirche_info.values() if k["quelle"] == "wikidata_via_gnd_kirche")
    via_pfarramt = sum(1 for k in kirche_info.values() if k["quelle"] == "kbb_pfarramt")
    print(f"{len(kirchen)} Kirchen mit Gebaeude-Koordinate ({via_wikidata} via GND/Wikidata, {via_pfarramt} via KBB-Pfarramt).")
    public_data_dir.mkdir(parents=True, exist_ok=True)
    (public_data_dir / "kirchen.json").write_text(
        json.dumps({"kirchen": kirchen}, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data", repo_root / "etl" / "cache", repo_root / "site" / "public" / "data")
