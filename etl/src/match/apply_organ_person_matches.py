"""Merge the organ<->person match cache into the organ shards, "sicher" only.

Run after organ_person_match.py has populated the cache:

    cd etl/src
    <venv>/Scripts/python.exe match/apply_organ_person_matches.py

Deliberately asymmetric compared to apply_gnd_matches.py/apply_bms_matches.py:
those keep every status (including "unsicher"/"keine") on the committed
record, because the UI itself decides what to render. Here only "sicher"
matches are written to `bauer_person_id` at all - "unsicher" cases are
reviewed via flag_doubtful_organ_person.py's Excel export and never reach
the committed site data until a person confirms them (at which point they'd
be re-classified, not silently included).
"""
from __future__ import annotations

import json
from pathlib import Path


def run(organs_dir: Path, cache_path: Path) -> None:
    matches: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    total = 0
    linked = 0
    for shard_path in sorted(organs_dir.glob("organs-*.json")):
        organs = json.loads(shard_path.read_text(encoding="utf-8"))
        changed = False
        for organ in organs:
            total += 1
            m = matches.get(str(organ["id"]))
            new_value = m["person_id"] if m and m["status"] == "sicher" else None
            if organ.get("bauer_person_id") != new_value:
                organ["bauer_person_id"] = new_value
                changed = True
            elif "bauer_person_id" not in organ:
                organ["bauer_person_id"] = new_value
                changed = True
            if new_value:
                linked += 1
        if changed:
            shard_path.write_text(json.dumps(organs, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{linked} von {total} Orgeln mit einer Person im Personenlexikon verknuepft (nur sichere Faelle).")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(
        repo_root / "site" / "src" / "data" / "organs",
        repo_root / "etl" / "cache" / "organ_person_matches.json",
    )


if __name__ == "__main__":
    main()
