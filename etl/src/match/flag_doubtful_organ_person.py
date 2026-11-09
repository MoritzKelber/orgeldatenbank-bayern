"""Export doubtful organ<->person cases as an Excel table for manual review.

Run after organ_person_match.py has populated the cache:

    cd etl/src
    <venv>/Scripts/python.exe match/flag_doubtful_organ_person.py

Lists every organ whose match is "unsicher" (surname found but the forename
didn't pick a single person) - "keine" (surname not found in the
Personenlexikon at all) is the expected, common case for a lexicon that
only covers ~1.650 of several thousand distinct builder names, same
reasoning as the other flag_doubtful_*.py scripts, and is not listed here.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def run(organs_dir: Path, builders_path: Path, cache_path: Path, reports_dir: Path) -> None:
    matches: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8"))
    lemmata = {b["id"]: b["name"] for b in json.loads(builders_path.read_text(encoding="utf-8"))}

    rows = []
    for shard_path in sorted(organs_dir.glob("organs-*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            m = matches.get(str(organ["id"]))
            if not m or m["status"] != "unsicher":
                continue
            rows.append(
                {
                    "organ_id": organ["id"],
                    "ort": organ.get("ort"),
                    "kirche": organ.get("kirche"),
                    "bauer_name": organ.get("bauer_name"),
                    "lemma": lemmata.get(m["lemma_id"]) if m.get("lemma_id") else None,
                    "grund": m.get("grund"),
                }
            )

    rows.sort(key=lambda r: (r["bauer_name"] or "", r["organ_id"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "Orgel-Person unsicher"
    headers = ["organ_id", "ort", "kirche", "bauer_name", "lemma", "grund"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[h] for h in headers])

    widths = [10, 22, 28, 32, 22, 55]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "orgel_personen_zweifelhafte_faelle.xlsx"
    wb.save(out_path)
    print(f"{len(rows)} zweifelhafte Orgel-Personen-Zuordnungen -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "organs",
        repo_root / "site" / "src" / "data" / "builders.json",
        repo_root / "etl" / "cache" / "organ_person_matches.json",
        repo_root / "etl" / "reports",
    )


if __name__ == "__main__":
    main()
