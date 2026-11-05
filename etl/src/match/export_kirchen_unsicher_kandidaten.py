"""Export every "unsicher" church-GND match with its FULL candidate list for manual review.

The cache only keeps the first candidate plus a truncated text note of up
to 3 others; this re-runs the same lobid query per "unsicher" entry to
recover the complete candidate set (lobid query size is 20), then writes
one row per candidate with a blank "auswahl" column for a human to mark
the correct one with an "x".

Run after gnd_match_kirchen.py / gnd_match_kirchen_refine.py:

    cd etl/src
    <venv>/Scripts/python.exe match/export_kirchen_unsicher_kandidaten.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from match.gnd_match_kirchen import REQUEST_INTERVAL_SECONDS, _collect_pairs, _query, core_tokens  # noqa: E402
from match.kirche_ortsteil import district_candidate  # noqa: E402


def run(site_data_dir: Path, cache_path: Path, reports_dir: Path) -> None:
    pairs = _collect_pairs(site_data_dir / "organs")
    matches = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    organ_count: dict[str, int] = defaultdict(int)
    for shard_path in sorted((site_data_dir / "organs").glob("*.json")):
        for organ in json.loads(shard_path.read_text(encoding="utf-8")):
            kirche = (organ.get("kirche") or "").strip()
            place_key = organ.get("place_key")
            if kirche and place_key:
                organ_count[f"{place_key}::{kirche}"] += 1

    unsicher_keys = [k for k, v in matches.items() if v.get("status") == "unsicher" and k in pairs]
    unsicher_keys.sort(key=lambda k: organ_count.get(k, 0), reverse=True)
    print(f"{len(unsicher_keys)} unsichere Kirchen-Zuordnungen - frage volle Kandidatenliste ab ...")

    rows: list[dict] = []
    for i, key in enumerate(unsicher_keys, start=1):
        p = pairs[key]
        tokens = core_tokens(p["kirche"])
        if not tokens:
            continue
        district = district_candidate(p["kirche"])
        place = district or p["ort"] or p["gemeinde"]
        try:
            candidates = _query(tokens[0], place)
        except Exception as exc:  # noqa: BLE001 - best effort, skip on failure
            print(f"[{i}/{len(unsicher_keys)}] {key}: Fehler ({exc}), uebersprungen")
            continue

        for rank, c in enumerate(candidates, start=1):
            rows.append(
                {
                    "kirche": p["kirche"],
                    "ort": p["ort"],
                    "landkreis": p.get("landkreis"),
                    "anzahl_orgeln_betroffen": organ_count.get(key, 0),
                    "kandidat_nr": rank,
                    "kandidat_name": c.get("preferredName"),
                    "kandidat_gnd_id": c.get("gndIdentifier"),
                    "kandidat_url": c.get("id"),
                    "auswahl": None,
                    "place_key_kirche": key,
                }
            )
        if i % 50 == 0:
            print(f"[{i}/{len(unsicher_keys)}] ...")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    wb = Workbook()
    ws = wb.active
    ws.title = "Kirchen unsicher - alle Kandidaten"
    headers = [
        "kirche", "ort", "landkreis", "anzahl_orgeln_betroffen", "kandidat_nr",
        "kandidat_name", "kandidat_gnd_id", "kandidat_url", "auswahl", "place_key_kirche",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[h] for h in headers])

    widths = [32, 18, 22, 12, 10, 42, 16, 32, 10, 40]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "kirchen_gnd_unsicher_alle_kandidaten.xlsx"
    wb.save(out_path)
    print(f"{len(rows)} Kandidaten-Zeilen fuer {len(unsicher_keys)} Kirchen -> {out_path}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data",
        repo_root / "etl" / "cache" / "gnd_kirchen_matches.json",
        repo_root / "etl" / "reports",
    )
