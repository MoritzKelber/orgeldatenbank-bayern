"""Fetch the official Bavarian "Ortslage" gazetteer (ATKIS Basis-DLM) via WFS.

Run once (then only to refresh - the dataset is maintained yearly):

    cd etl/src
    <venv>/Scripts/python.exe geocode/fetch_ortslage.py

AX_Ortslage is the Bavarian Surveying Administration's own layer of named
settlements/localities (villages, hamlets, Ortsteile) - a Bavaria-only,
authoritative counterpart to Nominatim's general-purpose, worldwide
search. It exists specifically to resolve two classes of problems found
in the Nominatim geocoding pass (see flag_doubtful.py):

- "not_found": small Ortsteile that Nominatim's address search misses
  entirely, but that the state's own survey data still names.
- "ok" but wrong state: Nominatim occasionally matches a same-named
  place in another German state when a small Bavarian locality isn't in
  its index; AX_Ortslage can only ever answer with a Bavarian place.

Source: geodaten.bayern.de/opengeodata (ATKIS Basis-DLM), licensed CC BY
4.0. The WFS ignores CQL_FILTER for this feature type, so this fetches
the whole layer (~24,000 features, ~120MB of GML) in one request rather
than querying per place - acceptable for a one-off/yearly refresh, and
kinder to the service than ~1,600 individual requests would be.

Output: etl/cache/bayern_ortslage_raw.json, a flat list of
[name, lat, lon] triples (one per polygon; the same locality can have
several entries where ATKIS recorded it as separate patches - callers
that need one point per name should average or pick by proximity).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

WFS_URL = "https://geoservices.bayern.de/wfs/v1/ogc_atkis_basisdlm.cgi"
GML_NS = "{http://www.opengis.net/gml/3.2}"
ADV_NS = "{http://www.adv-online.de/namespaces/adv/gid/7.1}"


def fetch_gml(out_path: Path) -> None:
    response = requests.get(
        WFS_URL,
        params={
            "SERVICE": "WFS",
            "REQUEST": "GetFeature",
            "VERSION": "2.0.0",
            "TYPENAMES": "adv:AX_Ortslage",
            "SRSNAME": "EPSG:4326",
        },
        timeout=300,
    )
    response.raise_for_status()
    out_path.write_bytes(response.content)


def parse_gml(gml_path: Path) -> list[tuple[str, float, float]]:
    results: list[tuple[str, float, float]] = []
    for _, elem in ET.iterparse(gml_path, events=("end",)):
        if elem.tag != f"{ADV_NS}AX_Ortslage":
            continue
        name_el = elem.find(f"{ADV_NS}name")
        name = name_el.text if name_el is not None else None
        lats, lons = [], []
        for poslist in elem.iter(f"{GML_NS}posList"):
            nums = poslist.text.split()
            for i in range(0, len(nums) - 1, 2):
                lats.append(float(nums[i]))
                lons.append(float(nums[i + 1]))
        if name and lats:
            results.append((name, sum(lats) / len(lats), sum(lons) / len(lons)))
        elem.clear()
    return results


def run(cache_dir: Path) -> None:
    gml_path = cache_dir / "bayern_ortslage.gml"
    print("Lade AX_Ortslage via WFS (ca. 120 MB, einmalig) ...")
    fetch_gml(gml_path)

    print("Parse Features ...")
    results = parse_gml(gml_path)
    print(f"{len(results)} benannte Ortslagen gefunden.")

    out_path = cache_dir / "bayern_ortslage_raw.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    gml_path.unlink()  # raw GML not needed once parsed, and too big to keep around
    print(f"Gespeichert nach {out_path}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "etl" / "cache")
