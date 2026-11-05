"""Merge the church GND match cache into site/src/data/organs/*.json.

Run after gnd_match_kirchen.py has (fully or partially) populated the cache:

    cd etl/src
    <venv>/Scripts/python.exe match/apply_gnd_kirchen.py

Same cache-then-merge shape as the other GND/geocoding steps: the slow,
network-dependent matching step writes an append-only cache keyed by
"<place_key>::<Kirche>", and this step cheaply sets each organ's
`kirche_gnd` field from it, safe to re-run after any match progress.
"""
from __future__ import annotations

import json
from pathlib import Path


def run(organs_dir: Path, cache_path: Path) -> None:
    matches = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    matched = 0
    total = 0
    for shard_path in sorted(organs_dir.glob("*.json")):
        organs = json.loads(shard_path.read_text(encoding="utf-8"))
        for organ in organs:
            total += 1
            kirche = (organ.get("kirche") or "").strip()
            place_key = organ.get("place_key")
            key = f"{place_key}::{kirche}" if kirche and place_key else None
            gnd = matches.get(key) if key else None
            organ["kirche_gnd"] = gnd
            if gnd and gnd["status"] == "ok":
                matched += 1
        shard_path.write_text(json.dumps(organs, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{matched} von {total} Orgeln mit sicherem Kirchen-GND-Treffer verknuepft.")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "organs",
        repo_root / "etl" / "cache" / "gnd_kirchen_matches.json",
    )


if __name__ == "__main__":
    main()
