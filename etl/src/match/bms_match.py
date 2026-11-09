"""Match literature catalog entries against the BMS (Bibliographie des
Musikschrifttums) via the GBV/K10plus SRU interface for the "bmsonline"
database.

Run after the literature catalog has been built:

    cd etl/src
    <venv>/Scripts/python.exe match/bms_match.py

musikbibliographie.de (the BMS web frontend) sits behind a JS proof-of-work
bot wall (Anubis) that blocks any non-browser client outright, so matching
goes through GBV's public SRU endpoint instead (http://sru.k10plus.de/
bmsonline), which is unprotected and returns structured PICA+ XML records.
The "BMS-ID" is the same identifier GBV calls a PPN (tag 003@/0) - confirmed
via the BMS-maintained BEACON link-dump files on
https://github.com/musikforschung/bms_beacon, whose #TARGET field points at
`https://www.musikbibliographie.de/REL?PPN=<id>`; the canonical, documented
K10plus permalink for a single record is `https://opac.k10plus.de/PPNSET?
PPN=<id>` (also blocked by the same bot wall for automated fetches, but not
for a real browser).

Query strategy: first author's surname (from our free-text AUTOR field,
split on "/" and ",") plus the first ~8 significant words of TITEL (falling
back to KURZTITEL), joined into one `pica.all="..."` phrase query - this
behaves as an implicit AND of terms (verified empirically: unrelated
queries reliably return 0 records, not loosely-ranked noise). Candidates
are then scored by title similarity (rapidfuzz against PICA tag 021A $a+$d,
stripped of PICA's "@" sort-marker) and, as tie-breakers, author-surname
overlap (028A/028B.../044K $A) and year proximity (PICA 011@ $a vs. the
best-guess year extracted from our own BIBLIO text).

Coverage is intentionally expected to be partial: the BMS indexes
musicological scholarship, not every local-history Festschrift or church
bulletin in our literature catalog, so "keine" is a normal, common outcome,
not a failure.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote
from xml.etree import ElementTree

import requests
from rapidfuzz import fuzz

SRU_URL = "http://sru.k10plus.de/bmsonline"
USER_AGENT = "orgeldatenbank-bayern-bms-matcher/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
REQUEST_INTERVAL_SECONDS = 0.5
TITLE_SCORE_THRESHOLD = 75  # rapidfuzz token_sort_ratio, 0-100
TITLE_SCORE_OK = 88
_PICA_NS = "{info:srw/schema/5/picaXML-v1.0}"
_ZS_NS = "{http://www.loc.gov/zing/srw/}"
_YEAR_IN_TEXT = re.compile(r"\b(1[4-9]\d{2}|20\d{2})\b")


class BmsMatch(TypedDict):
    status: str  # "ok" | "unsicher" | "keine"
    ppn: str | None
    url: str | None
    matched_titel: str | None
    matched_autor: str | None
    matched_jahr: int | None
    score: float | None
    grund: str | None
    isbn: list[str]  # PICA 004A $0 - monographs only, empty for journal articles


def _clean_title(raw: str | None) -> str:
    return (raw or "").replace("@", "").strip()


def _query(query: str, attempt: int = 1) -> list[dict]:
    url = f"{SRU_URL}?version=1.1&operation=searchRetrieve&query={quote(query)}&maximumRecords=5&recordSchema=picaxml"
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        if attempt >= 4:
            raise
        time.sleep(2 ** attempt)
        return _query(query, attempt + 1)

    # Parse raw bytes, not response.text - the server's Content-Type header
    # under-specifies charset, so requests' encoding auto-detection guesses
    # wrong and mangles umlauts; ElementTree reads the encoding from the
    # XML declaration itself and decodes correctly.
    root = ElementTree.fromstring(response.content)
    records = []
    for rec in root.iter(f"{_PICA_NS}record"):
        fields: dict[str, list[dict[str, str]]] = {}
        for df in rec.findall(f"{_PICA_NS}datafield"):
            tag = df.get("tag")
            subfields = {sf.get("code"): (sf.text or "") for sf in df.findall(f"{_PICA_NS}subfield")}
            fields.setdefault(tag, []).append(subfields)
        records.append(fields)
    return records


def _record_ppn(fields: dict) -> str | None:
    f = fields.get("003@")
    return f[0].get("0") if f else None


def _record_isbns(fields: dict) -> list[str]:
    return [sf["0"] for sf in fields.get("004A", []) if sf.get("0")]


def _record_title(fields: dict) -> str:
    f = fields.get("021A")
    if not f:
        return ""
    sf = f[0]
    return _clean_title(" ".join(filter(None, [sf.get("a"), sf.get("d")])))


def _record_year(fields: dict) -> int | None:
    f = fields.get("011@")
    if f and f[0].get("a") and f[0]["a"].isdigit():
        return int(f[0]["a"])
    for tag in ("031A",):
        for sf in fields.get(tag, []):
            if sf.get("j") and sf["j"].isdigit():
                return int(sf["j"])
    return None


def _record_authors(fields: dict) -> list[str]:
    """Surnames from the actual creator tags only (028A = first author,
    028B/028C... = further authors) - deliberately excludes 044K (subject
    person: the article is *about* them, not written by them), since that
    tag produced false author-overlaps against our own AUTOR field during
    testing (e.g. a generic "Neue Orgeln in Bayern" column-title record
    carrying unrelated subject/corporate terms in a person-tag slot)."""
    surnames = []
    for tag in ("028A", "028B", "028C"):
        for sf in fields.get(tag, []):
            if sf.get("A"):
                surnames.append(sf["A"])
    return surnames


def _our_authors(autor: str | None) -> list[str]:
    if not autor:
        return []
    return [re.split(r"[,]", part.strip(), maxsplit=1)[0].strip() for part in autor.split("/") if part.strip()]


def _our_year(biblio: str | None) -> int | None:
    if not biblio:
        return None
    years = [int(y) for y in _YEAR_IN_TEXT.findall(biblio)]
    return years[-1] if years else None


def _build_query(entry: dict) -> str | None:
    titel = entry.get("titel") or entry.get("kurztitel") or ""
    titel_words = " ".join(_clean_title(titel).split()[:8])
    if not titel_words:
        return None
    authors = _our_authors(entry.get("autor"))
    terms = ([authors[0]] if authors else []) + [titel_words]
    return f'pica.all="{" ".join(terms)}"'


def _score(entry: dict, fields: dict) -> dict:
    our_titel = _clean_title(entry.get("titel") or entry.get("kurztitel") or "")
    their_titel = _record_title(fields)
    title_score = fuzz.token_sort_ratio(our_titel.lower(), their_titel.lower())

    our_authors = {a.lower() for a in _our_authors(entry.get("autor"))}
    their_authors = {a.lower() for a in _record_authors(fields)}
    author_match = bool(our_authors & their_authors)

    our_year = _our_year(entry.get("biblio"))
    their_year = _record_year(fields)
    has_year_data = our_year is not None and their_year is not None
    year_match = has_year_data and abs(our_year - their_year) <= 1
    # Recurring column/series titles (e.g. "Neue Orgeln in Bayern", printed
    # once a year with a new volume/year every time) are the trap here: an
    # identical title every year scores 100 regardless of which year's
    # instalment BMS actually indexed, so a confirmed year mismatch must
    # veto "ok" outright rather than being something author_match can
    # outweigh - caught via a real example during testing (42 distinct
    # yearly entries all scoring title_score=100 against one BMS record
    # from an unrelated year).
    year_mismatch = has_year_data and not year_match

    return {
        "fields": fields,
        "title_score": title_score,
        "author_match": author_match,
        "year_match": year_match,
        "has_year_data": has_year_data,
        "year_mismatch": year_mismatch,
    }


def match_entry(entry: dict) -> BmsMatch:
    def _empty(status: str, grund: str | None) -> BmsMatch:
        return {
            "status": status, "ppn": None, "url": None, "matched_titel": None,
            "matched_autor": None, "matched_jahr": None, "score": None, "grund": grund, "isbn": [],
        }

    query = _build_query(entry)
    if query is None:
        return _empty("keine", None)

    records = _query(query)
    if not records:
        return _empty("keine", None)

    scored = sorted((_score(entry, f) for f in records), key=lambda s: s["title_score"], reverse=True)
    best = scored[0]
    close_runners_up = [s for s in scored[1:] if s["title_score"] >= best["title_score"] - 5]

    def _build(status: str, grund: str | None) -> BmsMatch:
        ppn = _record_ppn(best["fields"])
        authors = _record_authors(best["fields"])
        return {
            "status": status,
            "ppn": ppn,
            "url": f"https://opac.k10plus.de/PPNSET?PPN={ppn}" if ppn else None,
            "matched_titel": _record_title(best["fields"]) or None,
            "matched_autor": ", ".join(authors) or None,
            "matched_jahr": _record_year(best["fields"]),
            "score": best["title_score"],
            "grund": grund,
            "isbn": _record_isbns(best["fields"]) if status == "ok" else [],
        }

    if best["title_score"] < TITLE_SCORE_THRESHOLD:
        return _build("keine", None)

    # Hard veto, checked first and never overridable by author_match or a
    # high title score - see the comment on year_mismatch in _score().
    if best["year_mismatch"]:
        return _build(
            "unsicher",
            f"Titel ähnlich (Score {best['title_score']:.0f}), aber Erscheinungsjahr passt nicht zur Quelle "
            f"(BMS: {_record_year(best['fields'])})",
        )

    if not best["has_year_data"] and not best["author_match"]:
        return _build("unsicher", "Titel ähnlich, aber weder Autor noch Erscheinungsjahr zum Abgleich vorhanden")

    if close_runners_up and not (best["author_match"] or best["year_match"]):
        return _build(
            "unsicher",
            f"{len(close_runners_up)} weitere/r BMS-Kandidat(en) mit ähnlichem Titel, "
            "ohne Autor-/Jahresabgleich nicht sicher unterscheidbar",
        )

    if best["title_score"] < TITLE_SCORE_OK and not (best["author_match"] or best["year_match"]):
        return _build("unsicher", "Titel nur mittelmäßig ähnlich, kein Autor-/Jahresabgleich möglich")

    return _build("ok", None)


def run(literature_path: Path, cache_path: Path, refresh: bool) -> None:
    catalog = json.loads(literature_path.read_text(encoding="utf-8"))
    results: dict[str, BmsMatch] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    todo = [entry for entry in catalog if refresh or entry["slug"] not in results]
    print(f"{len(catalog)} Literatureintraege insgesamt, {len(results)} bereits im Cache, {len(todo)} werden abgefragt.")

    for done, entry in enumerate(todo, start=1):
        try:
            results[entry["slug"]] = match_entry(entry)
        except (requests.RequestException, ElementTree.ParseError) as exc:
            print(f"[{done}/{len(todo)}] {entry['slug']}: Fehler, wird im naechsten Lauf erneut versucht ({exc})")
            continue
        if done % 50 == 0:
            print(f"[{done}/{len(todo)}] ...")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter

    counts = Counter(r["status"] for r in results.values())
    print(f"Fertig. {dict(counts)} (von {len(catalog)} Eintraegen).")


if __name__ == "__main__":
    import argparse

    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Match literature catalog entries against BMS via GBV/K10plus SRU")
    parser.add_argument("--literature", default=str(repo_root / "site" / "src" / "data" / "literature.json"))
    parser.add_argument("--cache", default=str(repo_root / "etl" / "cache" / "bms_matches.json"))
    parser.add_argument("--refresh", action="store_true", help="auch bereits gecachte Eintraege neu abfragen")
    args = parser.parse_args()
    run(Path(args.literature), Path(args.cache), args.refresh)

