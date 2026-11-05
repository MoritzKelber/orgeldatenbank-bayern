"""Export doubtful/unmatched church-GND cases as an Excel table for review.

Run after match/apply_gnd_kirchen.py has merged the cache in:

    cd etl/src
    <venv>/Scripts/python.exe match/flag_doubtful_gnd_kirchen.py

Lists every church whose GND match is "unsicher" (several same-named
candidates) - but not "keine" (GND simply doesn't catalog most small
village churches; that is the expected majority outcome, not a gap worth
a line each) and not "nicht_zutreffend" (not a real church name to begin
with). Sorted by how many organs share that church, so review time goes
to the most-visible entries first.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def run(organs_dir: Path, cache_path: Path, reports_dir: Path) -> None:
    matches = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    seen: dict[str, dict] = {}
    organ_count: dict[str, int] = defaultdict(int)
    for shard_path in sorted(organs_dir.glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            kirche = (organ.get("kirche") or "").strip()
            place_key = organ.get("place_key")
            if not kirche or not place_key:
                continue
            key = f"{place_key}::{kirche}"
            organ_count[key] += 1
            if key not in seen:
                seen[key] = {"kirche": kirche, "ort": organ.get("ort"), "landkreis": organ.get("landkreis")}

    rows = []
    for key, info in seen.items():
        gnd = matches.get(key)
        if not gnd or gnd["status"] != "unsicher":
            continue
        rows.append(
            {
                "kirche": info["kirche"],
                "ort": info["ort"],
                "landkreis": info["landkreis"],
                "status": gnd["status"],
                "grund": gnd.get("grund"),
                "gnd_kandidat": gnd.get("preferred_name"),
                "gnd_url": gnd.get("url"),
                "anzahl_orgeln_betroffen": organ_count[key],
            }
        )
    rows.sort(key=lambda r: r["anzahl_orgeln_betroffen"], reverse=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Kirchen GND unsicher"
    headers = ["kirche", "ort", "landkreis", "status", "grund", "gnd_kandidat", "gnd_url", "anzahl_orgeln_betroffen"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[h] for h in headers])

    widths = [30, 20, 22, 10, 55, 40, 32, 14]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "kirchen_gnd_zweifelhafte_faelle.xlsx"
    wb.save(out_path)
    print(f"{len(rows)} zweifelhafte Kirchen-GND-Zuordnungen -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "organs",
        repo_root / "etl" / "cache" / "gnd_kirchen_matches.json",
        repo_root / "etl" / "reports",
    )


if __name__ == "__main__":
    main()
