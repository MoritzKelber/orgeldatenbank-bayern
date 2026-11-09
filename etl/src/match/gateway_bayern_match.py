"""Link literature catalog entries to their title record in Gateway
Bayern (the B3Kat union catalog of Bavarian academic libraries) via ISBN.

Run after match/apply_bms_matches.py has merged ISBNs extracted from BMS
into literature.json (see bms_match.py's "isbn" field - PICA 004A $0,
monographs only):

    cd etl/src
    <venv>/Scripts/python.exe match/gateway_bayern_match.py

Only entries with a confirmed BMS match ("ok") and at least one ISBN are
candidates - ISBN is an exact, checksum-validated identifier, so unlike
the BMS title/author/year matching this needs no fuzzy scoring: a hit is
a hit. Queries B3Kat's public SRU endpoint (bvbr.bib-bvb.de:5661/bvb01sru,
index marcxml.isbn - confirmed via its own SRU explain operation; the
musikbibliographie.de/gateway-bayern.de web frontends themselves sit
behind a JS proof-of-work bot wall that blocks any non-browser client).
The record's own MARC controlfield 001 (its "BV-Nr.") is the permalink
identifier, confirmed via the documented gateway-bayern.de/<BV-Nr>
resolver.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote
from xml.etree import ElementTree

import requests

SRU_URL = "http://bvbr.bib-bvb.de:5661/bvb01sru"
USER_AGENT = "orgeldatenbank-bayern-gateway-bayern-matcher/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
REQUEST_INTERVAL_SECONDS = 0.5
_MARC_NS = "{http://www.loc.gov/MARC21/slim}"
_ZS_NS = "{http://www.loc.gov/zing/srw/}"
_NON_DIGIT = re.compile(r"[^0-9Xx]")


class GatewayBayernMatch(TypedDict):
    status: str  # "ok" | "keine"
    bv_nr: str | None
    url: str | None
    isbn_used: str | None


def _query_by_isbn(isbn: str, attempt: int = 1) -> str | None:
    clean = _NON_DIGIT.sub("", isbn)
    url = f"{SRU_URL}?version=1.1&operation=searchRetrieve&query={quote(f'marcxml.isbn={clean}')}&maximumRecords=1&recordSchema=marcxml"
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        if attempt >= 4:
            raise
        time.sleep(2 ** attempt)
        return _query_by_isbn(isbn, attempt + 1)

    root = ElementTree.fromstring(response.content)
    n = root.findtext(f"{_ZS_NS}numberOfRecords")
    if not n or int(n) < 1:
        return None
    for cf in root.iter(f"{_MARC_NS}controlfield"):
        if cf.get("tag") == "001" and cf.text:
            return cf.text
    return None


def match_entry(bms: dict | None) -> GatewayBayernMatch:
    isbns = (bms or {}).get("isbn") or []
    if not bms or bms.get("status") != "ok" or not isbns:
        return {"status": "keine", "bv_nr": None, "url": None, "isbn_used": None}

    for isbn in isbns:
        bv_nr = _query_by_isbn(isbn)
        time.sleep(REQUEST_INTERVAL_SECONDS)
        if bv_nr:
            return {
                "status": "ok",
                "bv_nr": bv_nr,
                "url": f"https://gateway-bayern.de/{bv_nr}",
                "isbn_used": isbn,
            }
    return {"status": "keine", "bv_nr": None, "url": None, "isbn_used": None}


def run(literature_path: Path, cache_path: Path, refresh: bool) -> None:
    catalog = json.loads(literature_path.read_text(encoding="utf-8"))
    results: dict[str, GatewayBayernMatch] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    candidates = [e for e in catalog if (e.get("bms") or {}).get("status") == "ok" and (e.get("bms") or {}).get("isbn")]
    todo = [e for e in candidates if refresh or e["slug"] not in results]
    print(f"{len(candidates)} Eintraege mit BMS-ISBN, {len(results)} bereits im Cache, {len(todo)} werden abgefragt.")

    for done, entry in enumerate(todo, start=1):
        try:
            results[entry["slug"]] = match_entry(entry.get("bms"))
        except (requests.RequestException, ElementTree.ParseError) as exc:
            print(f"[{done}/{len(todo)}] {entry['slug']}: Fehler, wird im naechsten Lauf erneut versucht ({exc})")
            continue
        if done % 20 == 0:
            print(f"[{done}/{len(todo)}] ...")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    print(f"Fertig. {ok} von {len(candidates)} ISBN-Kandidaten mit Gateway-Bayern-Treffer.")


if __name__ == "__main__":
    import argparse

    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Link literature entries to Gateway Bayern (B3Kat) via ISBN")
    parser.add_argument("--literature", default=str(repo_root / "site" / "src" / "data" / "literature.json"))
    parser.add_argument("--cache", default=str(repo_root / "etl" / "cache" / "gateway_bayern_matches.json"))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    run(Path(args.literature), Path(args.cache), args.refresh)
