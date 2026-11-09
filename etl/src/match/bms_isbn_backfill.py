"""One-off backfill: add ISBN(s) to already-cached "ok" BMS matches.

bms_match.py now extracts ISBN (PICA 004A $0) as part of match_entry(), but
a cache written by an older run of that script won't have it. Rather than
re-running the whole fuzzy title/author/year matching pass, this re-fetches
each already-confirmed match directly by its own PPN (pica.ppn=<ppn>, an
exact single-record lookup, no scoring needed) and merges the ISBN list in.
Safe to re-run.

    cd etl/src
    <venv>/Scripts/python.exe match/bms_isbn_backfill.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # etl/src
from match.bms_match import USER_AGENT, SRU_URL, _PICA_NS, _record_isbns  # noqa: E402

REQUEST_INTERVAL_SECONDS = 0.3


def _fetch_by_ppn(ppn: str) -> dict | None:
    url = f"{SRU_URL}?version=1.1&operation=searchRetrieve&query={quote(f'pica.ppn={ppn}')}&maximumRecords=1&recordSchema=picaxml"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    for rec in root.iter(f"{_PICA_NS}record"):
        fields: dict[str, list[dict[str, str]]] = {}
        for df in rec.findall(f"{_PICA_NS}datafield"):
            tag = df.get("tag")
            subfields = {sf.get("code"): (sf.text or "") for sf in df.findall(f"{_PICA_NS}subfield")}
            fields.setdefault(tag, []).append(subfields)
        return fields
    return None


def run(cache_path: Path) -> None:
    results: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8"))
    todo = [k for k, v in results.items() if v.get("status") == "ok" and "isbn" not in v and v.get("ppn")]
    print(f"{len(todo)} bestaetigte BMS-Treffer ohne ISBN-Feld werden nachgetragen.")

    for done, key in enumerate(todo, start=1):
        ppn = results[key]["ppn"]
        try:
            fields = _fetch_by_ppn(ppn)
            results[key]["isbn"] = _record_isbns(fields) if fields else []
        except (requests.RequestException, ElementTree.ParseError) as exc:
            print(f"[{done}/{len(todo)}] {key} (PPN {ppn}): Fehler, uebersprungen ({exc})")
            continue
        if done % 50 == 0:
            print(f"[{done}/{len(todo)}] ...")
            cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    for v in results.values():
        v.setdefault("isbn", [])
    cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    with_isbn = sum(1 for v in results.values() if v.get("isbn"))
    print(f"Fertig. {with_isbn} Eintraege mit mind. einer ISBN.")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "etl" / "cache" / "bms_matches.json")


if __name__ == "__main__":
    main()
