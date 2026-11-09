"""Merge the BMS match cache into site/src/data/literature.json.

Run after bms_match.py has (fully or partially) populated the cache:

    cd etl/src
    <venv>/Scripts/python.exe match/apply_bms_matches.py

Same cache-then-merge shape as apply_gnd_matches.py: the slow,
network-dependent matching step writes an append-only cache, and this step
cheaply regenerates the site JSON from source + cache every time, so it is
safe to re-run after any bms_match.py progress.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def run(literature_path: Path, cache_path: Path) -> None:
    catalog = json.loads(literature_path.read_text(encoding="utf-8"))
    matches = load_json(cache_path, {})

    matched = 0
    for entry in catalog:
        bms = matches.get(entry["slug"])
        entry["bms"] = bms
        if bms and bms["status"] == "ok":
            matched += 1

    literature_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{matched} von {len(catalog)} Literatureintraegen mit sicherem BMS-Treffer verknuepft.")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "literature.json",
        repo_root / "etl" / "cache" / "bms_matches.json",
    )


if __name__ == "__main__":
    main()
