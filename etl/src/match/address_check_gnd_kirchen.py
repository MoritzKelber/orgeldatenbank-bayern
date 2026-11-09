"""Check church GND matches against the organ's street address.

    cd etl/src
    <venv>/Scripts/python.exe match/address_check_gnd_kirchen.py

Run after match/recheck_gnd_kirchen.py. The GND itself carries no street
address, so the address is used through the Wikidata item each GND record
is linked to (same route as geocode/build_kirchen_layer.py):

  * Wikidata gives a building coordinate (P625), often a postal code (P281)
    and sometimes a street address (P6375) for the candidate church.
  * The organ's own address (Strasse + Hausnummer, PLZ, Ort) is geocoded
    once via Nominatim (cached in etl/cache/address_geocode_cache.json).

Evidence per candidate:
  - PLZ: Wikidata postal code differs from the organ's PLZ -> contradiction.
  - Distance: geocoded address within 400 m of the building (house-number
    precision) / 800 m (street precision) -> confirmed; farther than 2 km
    -> contradiction.

Effect on etl/cache/gnd_kirchen_matches.json (field `adresse_pruefung`):
  - "ok" with a contradiction -> "unsicher" (a wrong link is worse than none).
  - "unsicher" with exactly one confirmed candidate -> "ok".
  - everything else unchanged; `adresse_pruefung` records what was found
    ("bestaetigt", "widerspruch", "keine_daten").
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from match.gnd_match_kirchen import _collect_pairs  # noqa: E402

SPARQL_URL = "https://query.wikidata.org/sparql"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "orgeldatenbank-bayern-address-check/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
_POINT = re.compile(r"Point\(([-\d.]+)\s+([-\d.]+)\)")
_GND_ID = re.compile(r"d-nb\.info/gnd/([0-9X-]+)")


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def fetch_wikidata(gnd_ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(gnd_ids), 150):
        batch = gnd_ids[i : i + 150]
        values = " ".join(f'"{g}"' for g in batch)
        query = f"""
            SELECT ?gnd ?coord ?plz ?street WHERE {{
              VALUES ?gnd {{ {values} }}
              ?item wdt:P227 ?gnd .
              OPTIONAL {{ ?item wdt:P625 ?coord . }}
              OPTIONAL {{ ?item wdt:P281 ?plz . }}
              OPTIONAL {{ ?item wdt:P6375 ?street . }}
            }}"""
        for attempt in range(1, 5):
            try:
                r = requests.get(SPARQL_URL, params={"query": query, "format": "json"},
                                 headers={"User-Agent": USER_AGENT}, timeout=60)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 4:
                    raise
                time.sleep(2**attempt)
        for b in r.json()["results"]["bindings"]:
            gid = b["gnd"]["value"]
            entry = out.setdefault(gid, {"coord": None, "plz": set(), "street": set()})
            if "coord" in b and (m := _POINT.search(b["coord"]["value"])):
                entry["coord"] = (float(m.group(2)), float(m.group(1)))  # lat, lon
            if "plz" in b:
                entry["plz"].add(b["plz"]["value"].strip())
            if "street" in b:
                entry["street"].add(b["street"]["value"].strip())
        time.sleep(1)
    return {g: {"coord": e["coord"], "plz": sorted(e["plz"]), "street": sorted(e["street"])} for g, e in out.items()}


def geocode_address(strasse: str | None, plz: str | None, ort: str | None, cache: dict) -> dict | None:
    if not (strasse and (plz or ort)):
        return None
    strasse = re.sub(r"(?<=[A-Za-zäöüß])\.(?=\d)", ". ", strasse)
    key = f"{strasse}|{plz}|{ort}"
    if key in cache:
        return cache[key]
    params = {"q": f"{strasse}, {plz or ''} {ort or ''}".strip(), "format": "json", "limit": 1,
              "countrycodes": "de", "addressdetails": 0}
    for attempt in range(1, 5):
        try:
            r = requests.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 4:
                return None
            time.sleep(2**attempt)
    hits = r.json()
    res = None
    if hits:
        h = hits[0]
        res = {"lat": float(h["lat"]), "lon": float(h["lon"]), "class": h.get("class"), "type": h.get("type")}
    cache[key] = res
    time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
    return res


def precision_radius(res: dict) -> float | None:
    """Tolerated distance in metres for a geocoder hit, or None when the hit is too coarse to use."""
    if res["class"] in ("building", "amenity", "place") and res["type"] in (
        "house", "yes", "place_of_worship", "church", "chapel", "cathedral", "monastery", "public_building"):
        return 400
    if res["class"] == "highway":
        return 800
    return None


def run(root: Path) -> None:
    cache_path = root / "etl" / "cache" / "gnd_kirchen_matches.json"
    geo_path = root / "etl" / "cache" / "address_geocode_cache.json"
    wd_path = root / "etl" / "cache" / "wikidata_kirchen_cache.json"
    matches: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8"))
    geo: dict = json.loads(geo_path.read_text(encoding="utf-8")) if geo_path.exists() else {}
    wd: dict = json.loads(wd_path.read_text(encoding="utf-8")) if wd_path.exists() else {}

    # first organ with a street address per (place_key, Kirche)
    address: dict[str, dict] = {}
    for shard in sorted((root / "site" / "src" / "data" / "organs").glob("*.json")):
        for organ in json.loads(shard.read_text(encoding="utf-8")):
            kirche, pk = (organ.get("kirche") or "").strip(), organ.get("place_key")
            a = organ.get("adresse") or {}
            if kirche and pk and a.get("zeile2"):
                address.setdefault(f"{pk}::{kirche}", a)

    def candidate_ids(m: dict) -> list[str]:
        ids = [m["gnd_id"]] if m.get("gnd_id") else []
        ids += _GND_ID.findall(m.get("grund") or "")
        return list(dict.fromkeys(ids))

    work = {k: m for k, m in matches.items() if m["status"] in ("ok", "unsicher") and k in address}
    need = sorted({g for m in work.values() for g in candidate_ids(m)} - set(wd))
    print(f"{len(work)} Kirchen mit Adresse und GND-Kandidat; {len(need)} Wikidata-Abfragen noetig.", flush=True)
    if need:
        fetched = fetch_wikidata(need)
        for g in need:
            wd[g] = fetched.get(g, {"coord": None, "plz": [], "street": []})
        wd_path.write_text(json.dumps(wd, ensure_ascii=False), encoding="utf-8")

    changed = {"widerspruch": 0, "bestaetigt": 0, "hochgestuft": 0, "herabgestuft": 0}
    for n, (key, m) in enumerate(work.items(), start=1):
        a = address[key]
        ids = candidate_ids(m)
        have_wd = [g for g in ids if wd.get(g, {}).get("coord") or wd.get(g, {}).get("plz")]
        verdicts: dict[str, str] = {}
        if have_wd:
            res = geocode_address(a.get("zeile2"), a.get("plz"), a.get("ort"), geo)
            radius = precision_radius(res) if res else None
            for g in have_wd:
                info = wd[g]
                if info["plz"] and a.get("plz") and a["plz"] not in info["plz"]:
                    verdicts[g] = "widerspruch"
                    continue
                if info["coord"] and res and radius:
                    d = haversine_m((res["lat"], res["lon"]), tuple(info["coord"]))
                    verdicts[g] = "bestaetigt" if d <= radius else ("widerspruch" if d > 2000 else "unklar")
                elif info["plz"] and a.get("plz") and a["plz"] in info["plz"]:
                    verdicts[g] = "bestaetigt"
        if n % 100 == 0:
            print(f"[{n}/{len(work)}] ...", flush=True)
            geo_path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")

        first = m.get("gnd_id")
        if m["status"] == "ok":
            v = verdicts.get(first)
            m["adresse_pruefung"] = v or "keine_daten"
            if v == "widerspruch":
                m["status"] = "unsicher"
                m["grund"] = f"Adresse ({a.get('zeile2')}, {a.get('plz')} {a.get('ort')}) passt nicht zum GND-/Wikidata-Eintrag"
                changed["herabgestuft"] += 1
            elif v == "bestaetigt":
                changed["bestaetigt"] += 1
        else:  # unsicher: exactly one candidate confirmed by the address, no other one not contradicted
            ok_ids = [g for g, v in verdicts.items() if v == "bestaetigt"]
            m["adresse_pruefung"] = "bestaetigt" if ok_ids else ("widerspruch" if verdicts else "keine_daten")
            if len(ok_ids) == 1:
                g = ok_ids[0]
                m.update({"status": "ok", "gnd_id": g, "url": f"https://d-nb.info/gnd/{g}",
                          "grund": None, "preferred_name": m["preferred_name"] if g == first else None})
                m["adresse_pruefung"] = "bestaetigt"
                changed["hochgestuft"] += 1

    geo_path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    cache_path.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Fertig:", changed, flush=True)


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
