"""Re-run the citation -> literature-catalog matching on the committed JSON.

    cd etl/src
    <venv>/Scripts/python.exe match/relink_literatur.py

transform/literatur_match.py learned to read page lists ("S.158, 213") and
serial volumes ("Kraus, Diözese Regensburg 4 (1987)" -> "... [Band] [Jahr]").
A full pipeline run would reset every later enrichment (BMS, GND, Gateway
Bayern, Digitalisate, geocoding ...), so this applies the better matching to
the existing shards instead: only citations that still have no slug are
touched, already linked ones are never changed.

Both sides of the link are updated together (organ["literatur"][i]["slug"]
and literature entry["organ_ids"]), so they cannot drift apart.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transform.literatur_match import build_lookup, match_literatur  # noqa: E402


def main() -> None:
    data = Path(__file__).resolve().parents[3] / "site" / "src" / "data"
    lit_path = data / "literature.json"
    catalog = json.loads(lit_path.read_text(encoding="utf-8"))
    by_kt = {e["kurztitel"].strip(): e for e in catalog if e.get("kurztitel")}
    kurztitel_set, kurztitel_list = build_lookup([{"KURZTITEL": k} for k in by_kt])
    added: dict[str, set[int]] = {}
    stats: Counter = Counter()
    cache: dict[str, dict] = {}

    for shard in sorted((data / "organs").glob("organs-*.json")):
        organs = json.loads(shard.read_text(encoding="utf-8"))
        changed = False
        for organ in organs:
            for cit in organ["literatur"]:
                if cit.get("slug") or not cit.get("lit"):
                    continue
                m = cache.get(cit["lit"]) or cache.setdefault(cit["lit"], match_literatur(cit["lit"], kurztitel_set, kurztitel_list))
                if not m["kurztitel"]:
                    continue
                entry = by_kt[m["kurztitel"]]
                cit["kurztitel"], cit["confidence"], cit["slug"] = m["kurztitel"], m["confidence"], entry["slug"]
                added.setdefault(entry["slug"], set()).add(organ["id"])
                stats[m["confidence"]] += 1
                changed = True
        if changed:
            shard.write_text(json.dumps(organs, ensure_ascii=False, indent=2), encoding="utf-8")

    for entry in catalog:
        new = added.get(entry["slug"])
        if new:
            entry["organ_ids"] = sorted(set(entry["organ_ids"]) | new)
    lit_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{sum(stats.values())} Verweise neu verknüpft {dict(stats)}; {len(added)} Literatureinträge betroffen.")


if __name__ == "__main__":
    main()
