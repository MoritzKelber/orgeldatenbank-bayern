"""Export doubtful/unmatched BMS cases from literature.json as an Excel table.

Run after match/apply_bms_matches.py has merged the BMS cache in:

    cd etl/src
    <venv>/Scripts/python.exe match/flag_doubtful_bms.py

Lists every literature entry whose BMS match is "unsicher" (title similar
but year/author don't line up, or several candidates not distinguishable)
- "keine" (no candidate at all) is the expected, common case for a
niche-literature catalog only partially covered by the BMS and is not
listed here, same reasoning as flag_doubtful_gnd.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def run(literature_path: Path, reports_dir: Path) -> None:
    catalog = json.loads(literature_path.read_text(encoding="utf-8"))

    rows = []
    for entry in catalog:
        bms = entry.get("bms")
        if not bms or bms["status"] != "unsicher":
            continue
        rows.append(
            {
                "slug": entry["slug"],
                "kurztitel": entry["kurztitel"],
                "autor": entry["autor"],
                "titel": entry["titel"],
                "biblio": entry["biblio"],
                "grund": bms.get("grund"),
                "bms_ppn": bms.get("ppn"),
                "bms_titel": bms.get("matched_titel"),
                "bms_autor": bms.get("matched_autor"),
                "bms_jahr": bms.get("matched_jahr"),
                "score": bms.get("score"),
            }
        )

    rows.sort(key=lambda r: r["kurztitel"])

    wb = Workbook()
    ws = wb.active
    ws.title = "BMS unsicher"
    headers = ["slug", "kurztitel", "autor", "titel", "biblio", "grund", "bms_ppn", "bms_titel", "bms_autor", "bms_jahr", "score"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[h] for h in headers])

    widths = [28, 28, 28, 40, 40, 55, 12, 32, 24, 10, 8]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "literatur_bms_zweifelhafte_faelle.xlsx"
    wb.save(out_path)
    print(f"{len(rows)} zweifelhafte BMS-Zuordnungen -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data" / "literature.json", repo_root / "etl" / "reports")


if __name__ == "__main__":
    main()
