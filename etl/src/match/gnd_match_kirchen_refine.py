"""Re-check doubtful church GND matches using the district name in parentheses.

Run after gnd_match_kirchen.py has populated the main cache:

    cd etl/src
    <venv>/Scripts/python.exe match/gnd_match_kirchen_refine.py

Only re-queries entries currently "unsicher" or "keine" whose Kirche text
has a parenthetical that looks like a real district name rather than a
building-type note (see kirche_ortsteil.py) - the first pass searched by
Ort/Gemeinde alone, which for a city like Munich returns dozens of
candidates and settles on "unsicher"; the district name is usually
exactly what GND itself uses to tell those churches apart
("Sankt Wolfgang (München-Haidhausen)"), so it is tried here as a second,
more specific place token. An upgrade only happens when the
district-qualified query is itself unambiguous (exactly one hit).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from match.gnd_match_kirchen import REQUEST_INTERVAL_SECONDS, _collect_pairs, _query, core_tokens  # noqa: E402
from match.kirche_ortsteil import district_candidate  # noqa: E402


def run(site_data_dir: Path, cache_path: Path) -> None:
    pairs = _collect_pairs(site_data_dir / "organs")
    results = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    targets = [
        key for key, p in pairs.items()
        if results.get(key, {}).get("status") in ("unsicher", "keine")
        and district_candidate(p["kirche"])
    ]
    print(f"{len(targets)} Kirchen mit Stadtteil-Hinweis werden erneut geprueft.")

    upgraded = 0
    for done, key in enumerate(targets, start=1):
        p = pairs[key]
        tokens = core_tokens(p["kirche"])
        district = district_candidate(p["kirche"])
        if not tokens or not district:
            continue
        try:
            candidates = _query(tokens[0], district)
        except requests.RequestException as exc:
            print(f"[{done}/{len(targets)}] {key}: Netzwerkfehler, uebersprungen ({exc})")
            time.sleep(REQUEST_INTERVAL_SECONDS)
            continue

        if len(candidates) == 1:
            c = candidates[0]
            results[key] = {
                "status": "ok", "gnd_id": c.get("gndIdentifier"), "url": c.get("id"),
                "preferred_name": c.get("preferredName"), "candidates_considered": 1,
                "grund": None,
            }
            upgraded += 1
        elif len(candidates) > 1:
            c = candidates[0]
            others = ", ".join(f"{m.get('preferredName')} ({m.get('id')})" for m in candidates[1:4])
            results[key] = {
                "status": "unsicher", "gnd_id": c.get("gndIdentifier"), "url": c.get("id"),
                "preferred_name": c.get("preferredName"), "candidates_considered": len(candidates),
                "grund": f"auch mit Stadtteil '{district}' mehrdeutig, u.a.: {others}",
            }
        # 0 candidates with the district token: leave the original result untouched.

        if done % 50 == 0:
            print(f"[{done}/{len(targets)}] ... ({upgraded} bisher aufgeloest)")
            cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fertig. {upgraded} von {len(targets)} durch den Stadtteil-Hinweis eindeutig aufgeloest.")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data", repo_root / "etl" / "cache" / "gnd_kirchen_matches.json")
