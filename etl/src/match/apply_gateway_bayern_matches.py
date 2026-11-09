"""Merge the Gateway Bayern (B3Kat) match cache into literature.json.

Run after gateway_bayern_match.py has (fully or partially) populated the
cache:

    cd etl/src
    <venv>/Scripts/python.exe match/apply_gateway_bayern_matches.py
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
        gw = matches.get(entry["slug"])
        entry["gateway_bayern"] = gw
        if gw and gw["status"] == "ok":
            matched += 1

    literature_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{matched} Literatureintraege mit Gateway-Bayern-Treffer verknuepft.")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "literature.json",
        repo_root / "etl" / "cache" / "gateway_bayern_matches.json",
    )


if __name__ == "__main__":
    main()
