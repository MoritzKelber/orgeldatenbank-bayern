"""Re-validate all church GND matches with the strict check and re-query
the ones that fail it (see gnd_kirchen_strict.py for the reasons).

    cd etl/src
    <venv>/Scripts/python.exe match/recheck_gnd_kirchen.py

1. Every cached "ok"/"unsicher" match is checked offline against the
   organ's Kirche/Ort/Gemeinde. Failing "ok" matches are dropped.
2. Dropped matches and all "unsicher" ones are re-queried (dedication word
   + Ort / Gemeinde / Stadtteil) and the lobid hits filtered through the
   same strict check: exactly one surviving candidate -> "ok", several ->
   "unsicher", none -> "keine".

Writes etl/cache/gnd_kirchen_matches.json and a review list
etl/reports/kirchen_gnd_neupruefung.md. Afterwards run
match/apply_gnd_kirchen.py and geocode/build_kirchen_layer.py.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from match.gnd_match_kirchen import LOBID_URL, REQUEST_INTERVAL_SECONDS, USER_AGENT, _collect_pairs, core_tokens  # noqa: E402
from match.gnd_kirchen_strict import verdict  # noqa: E402
from match.kirche_ortsteil import district_candidate  # noqa: E402


def query_all(token: str, place: str, attempt: int = 1) -> list[dict]:
    q = f'type:BuildingOrMemorial AND geographicAreaCode.label:Bayern AND preferredName:*{token}* AND preferredName:*{place}*'
    try:
        r = requests.get(LOBID_URL, params={"q": q, "format": "json", "size": 100},
                         headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        return r.json().get("member", [])
    except requests.RequestException:
        if attempt >= 4:
            raise
        time.sleep(2**attempt)
        return query_all(token, place, attempt + 1)


def requery(p: dict) -> dict:
    kirche, ort, gemeinde = p["kirche"], p["ort"], p["gemeinde"]
    ded = core_tokens(kirche)
    if not ded or not ort:
        return {"status": "nicht_zutreffend", "gnd_id": None, "url": None, "preferred_name": None,
                "candidates_considered": 0, "grund": "kein nutzbarer Widmungsname"}
    places = [ort]
    if gemeinde and gemeinde != ort:
        places.append(gemeinde)
    hint = district_candidate(kirche)
    if hint:
        places.append(hint)
    seen: dict[str, dict] = {}
    rejected: list[str] = []
    for place in places:
        for member in query_all(ded[0], place):
            gid = member.get("gndIdentifier")
            if gid in seen:
                continue
            v, why = verdict(kirche, ort, gemeinde, member.get("preferredName") or "")
            if v == "pass":
                seen[gid] = member
            elif len(rejected) < 3:
                rejected.append(f"{member.get('preferredName')} ({why.split(':')[0]})")
        time.sleep(REQUEST_INTERVAL_SECONDS)
    cands = list(seen.values())
    if not cands:
        return {"status": "keine", "gnd_id": None, "url": None, "preferred_name": None,
                "candidates_considered": 0, "grund": None}
    c = cands[0]
    base = {"gnd_id": c.get("gndIdentifier"), "url": c.get("id"), "preferred_name": c.get("preferredName"),
            "candidates_considered": len(cands)}
    if len(cands) == 1:
        return {"status": "ok", **base, "grund": None}
    others = ", ".join(f"{m.get('preferredName')} ({m.get('id')})" for m in cands[1:4])
    return {"status": "unsicher", **base, "grund": f"{len(cands)} passende Kandidaten, u.a.: {others}"}


def run(site_data_dir: Path, cache_path: Path, report_path: Path) -> None:
    pairs = _collect_pairs(site_data_dir / "organs")
    cache: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8"))

    todo: list[str] = []
    dropped: list[tuple[str, dict, str]] = []
    for key, m in cache.items():
        p = pairs.get(key)
        if not p or m["status"] not in ("ok", "unsicher"):
            continue
        if m["status"] == "unsicher":
            todo.append(key)
            continue
        v, why = verdict(p["kirche"], p["ort"], p["gemeinde"], m.get("preferred_name") or "")
        if v != "pass":
            dropped.append((key, m, why))
            todo.append(key)
    print(f"{len(dropped)} bisherige 'ok'-Treffer fallen durch die strenge Pruefung; "
          f"{len(todo)} Kirchen werden neu abgefragt.", flush=True)

    old = {key: dict(cache[key]) for key in todo}
    for n, key in enumerate(todo, start=1):
        try:
            cache[key] = requery(pairs[key])
        except requests.RequestException as exc:
            print(f"[{n}/{len(todo)}] {key}: Netzwerkfehler, alter Stand bleibt ({exc})", flush=True)
            continue
        if n % 50 == 0:
            print(f"[{n}/{len(todo)}] ...", flush=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    print("Neu:", dict(Counter(m["status"] for m in cache.values())), flush=True)

    lines = ["# Neupruefung der Kirchen-GND-Zuordnung", "",
             "Frueher 'ok', jetzt verworfen oder geaendert (Grund der strengen Pruefung, neuer Stand):", ""]
    for key, m, why in dropped:
        new = cache[key]
        lines.append(f"- **{key}** - war: {m.get('preferred_name')} - {why} -> jetzt: {new['status']}"
                     + (f" ({new.get('preferred_name')})" if new.get("preferred_name") else ""))
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Bericht: {report_path}", flush=True)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    run(root / "site" / "src" / "data", root / "etl" / "cache" / "gnd_kirchen_matches.json",
        root / "etl" / "reports" / "kirchen_gnd_neupruefung.md")
