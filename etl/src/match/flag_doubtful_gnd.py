"""Export doubtful/unmatched GND cases from builders.json as an Excel table.

Run after match/apply_gnd_matches.py has merged the GND cache in:

    cd etl/src
    <venv>/Scripts/python.exe match/flag_doubtful_gnd.py

Lists every person whose GND match is "unsicher" (ambiguous candidates,
date mismatch, or only found without the GND occupation tag) or "keine"
(no candidate at all) - but not "nicht_zutreffend" (firms/collectives,
where a GND person match was never applicable, not a gap). Sorted so
lemmata that bundle several people appear together, for fast review.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def run(builders_path: Path, reports_dir: Path) -> None:
    lemmata = json.loads(builders_path.read_text(encoding="utf-8"))

    rows = []
    for lemma in lemmata:
        for p in lemma.get("personen", []):
            gnd = p.get("gnd")
            if not gnd or gnd["status"] not in ("unsicher", "keine"):
                continue
            rows.append(
                {
                    "lemma_id": lemma["id"],
                    "lemma_name": lemma["name"],
                    "person_index": p["index"],
                    "name": p["name_raw"],
                    "lebensdaten_quelle": "; ".join(p["lebensdaten"]["raw"]) or None,
                    "status": gnd["status"],
                    "grund": gnd.get("grund"),
                    "gnd_kandidat": gnd.get("preferred_name"),
                    "gnd_url": gnd.get("url"),
                    "name_score": gnd.get("name_score"),
                    "kandidaten_geprueft": gnd.get("candidates_considered"),
                }
            )

    rows.sort(key=lambda r: (r["lemma_id"], r["person_index"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "GND unsicher-keine"
    headers = [
        "lemma_id", "lemma_name", "person_index", "name", "lebensdaten_quelle", "status",
        "grund", "gnd_kandidat", "gnd_url", "name_score", "kandidaten_geprueft",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[h] for h in headers])

    widths = [10, 20, 12, 32, 30, 10, 55, 28, 32, 10, 14]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "erbauer_gnd_zweifelhafte_faelle.xlsx"
    wb.save(out_path)
    print(f"{len(rows)} zweifelhafte/fehlende GND-Zuordnungen -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data" / "builders.json", repo_root / "etl" / "reports")


if __name__ == "__main__":
    main()
