"""Check that the cross-links between organs, persons and literature agree.

    cd etl/src
    <venv>/Scripts/python.exe validate_sync.py

Exit code 1 if a link points nowhere or exists on one side only:

  * organ["literatur"][i]["slug"]  <->  literature entry["organ_ids"]
  * organ["bauer_id"]              <->  builder["organ_ids"]
  * organ["bauer_person_id"]       ->   an existing person ("{lemma}-{index}")
  * builder["literatur"][i]["slug"] <-> literature entry["lemma_ids"]

Also prints coverage figures (how many citations / builder names are linked)
so a regression in the matchers is visible.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    data = Path(__file__).resolve().parents[2] / "site" / "src" / "data"
    organs = [o for f in sorted((data / "organs").glob("organs-*.json")) for o in json.loads(f.read_text(encoding="utf-8"))]
    lit = json.loads((data / "literature.json").read_text(encoding="utf-8"))
    builders = json.loads((data / "builders.json").read_text(encoding="utf-8"))
    slugs = {e["slug"] for e in lit}
    lemmata = {b["id"]: b for b in builders}
    persons = {f'{b["id"]}-{p["index"]}' for b in builders for p in b["personen"]}
    errors: list[str] = []

    fw = {(o["id"], c["slug"]) for o in organs for c in o["literatur"] if c.get("slug")}
    rv = {(i, e["slug"]) for e in lit for i in e["organ_ids"]}
    errors += [f"Orgel↔Literatur nur auf Orgelseite: {p}" for p in sorted(fw - rv)[:5]]
    errors += [f"Orgel↔Literatur nur auf Literaturseite: {p}" for p in sorted(rv - fw)[:5]]
    errors += [f"Literatur-slug unbekannt: {s}" for _, s in sorted(fw) if s not in slugs][:5]

    fb = {(o["id"], o["bauer_id"]) for o in organs if o.get("bauer_id")}
    rb = {(i, b["id"]) for b in builders for i in b["organ_ids"]}
    errors += [f"Orgel↔Erbauer-Lemma nur einseitig: {p}" for p in sorted(fb ^ rb)[:5]]
    errors += [f"bauer_person_id unbekannt: {o['bauer_person_id']} (Orgel {o['id']})"
               for o in organs if o.get("bauer_person_id") and o["bauer_person_id"] not in persons][:5]

    fl = {(b["id"], r["slug"]) for b in builders for r in b.get("literatur", []) if r.get("slug")}
    rl = {(lid, e["slug"]) for e in lit for lid in e.get("lemma_ids", [])}
    errors += [f"Person↔Literatur nur einseitig: {p}" for p in sorted(fl ^ rl)[:5]]
    errors += [f"lemma_id unbekannt: {lid}" for e in lit for lid in e.get("lemma_ids", []) if lid not in lemmata][:5]

    cites = [c for o in organs for c in o["literatur"]]
    conf = Counter(c["confidence"] for c in cites)
    with_name = [o for o in organs if o.get("bauer_name")]
    print(f"Literaturverweise an Orgeln: {len(cites)}, verknüpft {sum(1 for c in cites if c.get('slug'))} {dict(conf)}")
    print(f"Orgeln mit Erbauername: {len(with_name)}, mit Person verknüpft {sum(1 for o in with_name if o.get('bauer_person_id'))}")
    print(f"Lit.-Zeilen in Biografien verknüpft: {len(fl)} Paare bei {len({b for b, _ in fl})} Lemmata")
    print(f"Literatureinträge ohne jeden Verweis (Orgel/Person): "
          f"{sum(1 for e in lit if not e['organ_ids'] and not e.get('lemma_ids'))} von {len(lit)}")
    for e in errors:
        print("FEHLER:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
