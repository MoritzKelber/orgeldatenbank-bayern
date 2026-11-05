"""Find doubtful geocoding results and export them as an Excel table for review.

Run after geocode.py has finished (or on a partial cache, to check progress
so far):

    cd etl/src
    <venv>/Scripts/python.exe geocode/flag_doubtful.py

A result is flagged as "zweifelhaft" when any of these hold:
- status is "not_found" or "error" (Nominatim found nothing or the request failed).
- the coordinate falls outside Bavaria's bounding box (a same-named place in
  another German state/country was matched instead).
- the Nominatim display_name doesn't mention Bavaria at all (secondary signal;
  border-region results sometimes legitimately omit it, so this alone doesn't
  make a result wrong, but it's worth a human glance).
- crosscheck_ortslage.py found a moderate (5-50km) distance between the
  Nominatim point and the nearest same-named AX_Ortslage locality - plausibly
  a same-name mix-up *within* Bavaria that the bbox/Bayern-mention checks
  above cannot see, but not a large enough gap to auto-correct blindly.

Output: etl/reports/geocoding_zweifelhafte_faelle.xlsx, one row per flagged
place_key, sorted by number of affected organs (most impactful first) so
manual review time goes to the cases that matter most.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from geocode.geocode import collect_places  # noqa: E402

# Generous bounding box around Bavaria (incl. border margin), WGS84 degrees.
BAVARIA_BBOX = {"lat_min": 47.2, "lat_max": 50.7, "lon_min": 8.9, "lon_max": 13.9}


def load_json(path: Path, default):
    import json

    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def classify(key: str, place: dict, geo: dict | None, distance_review: dict) -> str | None:
    """Return a reason string if doubtful, else None."""
    if geo is None:
        return "nicht abgefragt (Geocoding noch nicht durchgelaufen)"
    status = geo.get("status")
    if status == "not_found":
        return "kein Nominatim-Treffer"
    if status == "error":
        return f"Fehler bei Anfrage: {geo.get('reason', '?')}"
    if status != "ok":
        return f"unbekannter Status: {status}"

    if geo.get("quelle") in ("bayern_ortslage", "wikidata_via_gnd_kirche", "manuell"):
        # Resolved via the Bavarian Surveying Administration's own
        # Ortslage gazetteer (see crosscheck_ortslage.py), a GND-matched
        # church's own surveyed Wikidata position (see
        # refine_via_kirchen.py), or a human-checked manual override
        # (etl/cache/geocode_overrides.json) - all are, by construction,
        # real Bavarian locations more precise than a Nominatim village match,
        # so the Nominatim-oriented bbox/"Bayern"-mention heuristics below
        # don't apply and would just re-flag an already-fixed case.
        return None

    reasons = []
    lat, lon = geo.get("lat"), geo.get("lon")
    if lat is None or lon is None or not (
        BAVARIA_BBOX["lat_min"] <= lat <= BAVARIA_BBOX["lat_max"]
        and BAVARIA_BBOX["lon_min"] <= lon <= BAVARIA_BBOX["lon_max"]
    ):
        reasons.append("Koordinate außerhalb Bayerns")

    display_name = (geo.get("display_name") or "").lower()
    if "bayern" not in display_name and "bavaria" not in display_name:
        reasons.append("Bayern wird im Nominatim-Ergebnis nicht erwähnt")

    review = distance_review.get(key)
    if review:
        reasons.append(f"liegt {review['distanz_km']}km von der naechsten AX_Ortslage mit diesem Namen entfernt")

    return "; ".join(reasons) if reasons else None


def run(site_data_dir: Path, cache_dir: Path, reports_dir: Path) -> None:
    organs_dir = site_data_dir / "organs"
    cache = load_json(cache_dir / "geocode_cache.json", {})
    overrides = load_json(cache_dir / "geocode_overrides.json", {})
    geocoded = {**cache, **overrides}
    distance_review = load_json(cache_dir / "ortslage_distance_review.json", {})

    places = collect_places(organs_dir)

    organ_count: dict[str, int] = defaultdict(int)
    for shard_path in sorted(organs_dir.glob("*.json")):
        import json

        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            key = organ.get("place_key")
            if key:
                organ_count[key] += 1

    rows = []
    for key, place in places.items():
        geo = geocoded.get(key)
        reason = classify(key, place, geo, distance_review)
        if reason is None:
            continue
        rows.append(
            {
                "place_key": key,
                "ort": place.get("ort"),
                "plz": place.get("plz"),
                "gemeinde": place.get("gemeinde"),
                "landkreis": place.get("landkreis"),
                "status": (geo or {}).get("status", "fehlt"),
                "lat": (geo or {}).get("lat"),
                "lon": (geo or {}).get("lon"),
                "nominatim_display_name": (geo or {}).get("display_name"),
                "grund": reason,
                "anzahl_orgeln_betroffen": organ_count.get(key, 0),
            }
        )

    rows.sort(key=lambda r: r["anzahl_orgeln_betroffen"], reverse=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Zweifelhafte Faelle"
    headers = [
        "place_key", "ort", "plz", "gemeinde", "landkreis", "status", "lat", "lon",
        "nominatim_display_name", "grund", "anzahl_orgeln_betroffen",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[h] for h in headers])

    widths = [22, 20, 8, 20, 22, 10, 10, 10, 60, 45, 12]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "geocoding_zweifelhafte_faelle.xlsx"
    wb.save(out_path)
    print(f"{len(rows)} zweifelhafte Orte (von {len(places)} insgesamt) -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data",
        repo_root / "etl" / "cache",
        repo_root / "etl" / "reports",
    )


if __name__ == "__main__":
    main()
