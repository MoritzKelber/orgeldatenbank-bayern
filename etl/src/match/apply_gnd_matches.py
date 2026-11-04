"""Merge the GND match cache into site/src/data/builders.json.

Run after gnd_match.py has (fully or partially) populated the cache:

    cd etl/src
    <venv>/Scripts/python.exe match/apply_gnd_matches.py

Same cache-then-merge shape as geocode.py/build_places.py: the slow,
network-dependent matching step writes an append-only cache, and this step
cheaply regenerates the site JSON from source + cache every time, so it is
safe to re-run after any gnd_match.py progress.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def run(builders_path: Path, cache_path: Path) -> None:
    lemmata = json.loads(builders_path.read_text(encoding="utf-8"))
    matches = load_json(cache_path, {})

    matched = 0
    total = 0
    for lemma in lemmata:
        for person in lemma["personen"]:
            total += 1
            key = f"{lemma['id']}-{person['index']}"
            gnd = matches.get(key)
            person["gnd"] = gnd
            if gnd and gnd["status"] == "ok":
                matched += 1

    builders_path.write_text(json.dumps(lemmata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{matched} von {total} Personen mit sicherem GND-Treffer verknüpft.")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "builders.json",
        repo_root / "etl" / "cache" / "gnd_matches.json",
    )


if __name__ == "__main__":
    main()
