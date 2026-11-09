"""Link literature entries to Gateway Bayern (B3Kat) by title, author and year.

    cd etl/src
    <venv>/Scripts/python.exe match/gateway_titel_match.py            # search (cached)
    <venv>/Scripts/python.exe match/gateway_titel_match.py --apply    # merge into literature.json

gateway_bayern_match.py only reaches entries whose BMS record carries an
ISBN. This searches the B3Kat SRU interface (bvbr.bib-bvb.de:5661/bvb01sru,
indexes marcxml.title / creator / date) for every other entry and accepts a
record only when title, author and year all agree:

  * title: our "Titel" and the MARC 245 ($a $b $n $p) are, after folding case,
    umlauts and punctuation, equal / one contains the other / all significant
    words of ours occur in the catalog title (score >= 0.85);
  * author: a surname from our "Autor" occurs in MARC 100/700 (or 110/710);
    entries without a real author ("Anonym", empty) are checked on title+year;
  * year: the year in our Kurztitel "(1982)" occurs in MARC 260/264 $c (+-1).
    No year on our side -> not checked; a different year -> rejected (another
    edition is not the cited book);
  * only monographs (MARC leader/07 = 'm'); journal articles are not
    catalogued as titles here and stay unlinked.

The permalink is https://gateway-bayern.de/<BV-Nr.> (MARC 001), the same
resolver the ISBN route uses. Result per slug in
etl/cache/gateway_titel_matches.json:
  {"status": "ok"|"keine"|"mehrdeutig", "bv_nr", "url", "titel", "score", ...}
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

import requests

SRU_URL = "http://bvbr.bib-bvb.de:5661/bvb01sru"
USER_AGENT = "orgeldatenbank-bayern-gateway-bayern-matcher/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
INTERVAL = 0.5
M = "{http://www.loc.gov/MARC21/slim}"
Z = "{http://www.loc.gov/zing/srw/}"
_STOP = {"der", "die", "das", "und", "in", "von", "zu", "mit", "fur", "im", "am", "an", "auf", "den", "dem", "des",
         "ein", "eine", "einer", "zur", "zum", "aus", "bei", "ueber", "uber", "the", "of", "and", "a"}


def fold(text: str) -> str:
    text = text.lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text)


def words(text: str) -> list[str]:
    return [w for w in fold(text).split() if w not in _STOP]


def clean_title(t: str) -> str:
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"\([^)]*\)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def surnames(autor: str | None) -> list[str]:
    if not autor or autor.strip().lower().startswith("anonym"):
        return []
    out = []
    for part in re.split(r"[/;]| und ", autor):
        s = part.split(",")[0].strip()
        s = re.sub(r"^(Hrsg\.|Hg\.)\s*", "", s)
        if len(s) >= 3:
            out.append(fold(s).strip())
    return out


def year_of(kurztitel: str) -> int | None:
    m = re.search(r"\((?:ca\.\s*)?(\d{4})(?:/\d+)?\??\)", kurztitel or "")
    return int(m.group(1)) if m else None


def sru(query: str, attempt: int = 1) -> ElementTree.Element:
    url = f"{SRU_URL}?version=1.1&operation=searchRetrieve&query={quote(query)}&maximumRecords=15&recordSchema=marcxml"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        return ElementTree.fromstring(r.content)
    except (requests.RequestException, ElementTree.ParseError):
        if attempt >= 4:
            raise
        time.sleep(2**attempt)
        return sru(query, attempt + 1)


def records(root: ElementTree.Element) -> list[dict]:
    out = []
    for rec in root.iter(M + "record"):
        d: dict = {"id": None, "leader": rec.findtext(M + "leader") or "", "title": "", "people": [], "years": []}
        for cf in rec.findall(M + "controlfield"):
            if cf.get("tag") == "001":
                d["id"] = cf.text
        for df in rec.findall(M + "datafield"):
            tag = df.get("tag")
            subs = {sf.get("code"): (sf.text or "") for sf in df.findall(M + "subfield")}
            if tag == "245":
                d["title"] = " ".join(df_sf.text or "" for df_sf in df.findall(M + "subfield") if df_sf.get("code") in "abnp")
            elif tag in ("100", "700", "110", "710"):
                d["people"].append(subs.get("a", ""))
            elif tag in ("260", "264"):
                d["years"] += [int(y) for y in re.findall(r"\d{4}", subs.get("c", ""))]
        out.append(d)
    return out


def title_score(ours: str, theirs: str) -> float:
    a, b = " ".join(words(clean_title(ours))), " ".join(words(clean_title(theirs)))
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa, sb = set(a.split()), set(b.split())
    if sa <= sb or sb <= sa:
        # Teilmenge nur, wenn der kuerzere Titel mindestens drei Woerter hat und
        # mindestens halb so lang ist wie der laengere ("Das Haus Gottes" darf
        # nicht in einem beliebigen Sammeltitel aufgehen).
        if min(len(sa), len(sb)) >= 3 and min(len(sa), len(sb)) / max(len(sa), len(sb)) >= 0.5:
            return 0.92
    return SequenceMatcher(None, a, b).ratio()


def judge(entry: dict, cand: dict, names: list[str], year: int | None) -> float | None:
    if cand["leader"][7:8] != "m" or cand["leader"][6:7] not in ("a", "t"):  # Monografie, Text (keine Tontraeger)
        return None
    s = title_score(entry["titel"] or entry["kurztitel"], cand["title"])
    if s < 0.85:
        return None
    if names:
        people = fold(" ".join(cand["people"]))
        if not any(n in people for n in names):
            return None
    if year is not None and cand["years"] and not any(abs(y - year) <= 1 for y in cand["years"]):
        return None
    if not names and year is None and s < 1.0:  # weder Autor noch Jahr pruefbar: nur exakter Titel
        return None
    return s


def search(entry: dict) -> dict:
    titel = entry.get("titel") or ""
    if not titel or titel.lower().startswith(("rez", "rezension")):
        return {"status": "keine"}
    ws = [w for w in words(clean_title(titel)) if len(w) >= 3][:4]
    if not ws:
        return {"status": "keine"}
    names = surnames(entry.get("autor"))
    year = year_of(entry.get("kurztitel") or "")
    parts = [f"marcxml.title = {w}" for w in ws]
    if names:
        parts.append(f"marcxml.creator = {names[0].split()[-1]}")
    elif year:
        parts.append(f"marcxml.date = {year}")
    root = sru(" and ".join(parts))
    scored = []
    for cand in records(root):
        s = judge(entry, cand, names, year)
        if s is not None and cand["id"]:
            scored.append((s, cand))
    if not scored:
        return {"status": "keine"}
    scored.sort(key=lambda x: -x[0])
    best = scored[0]
    ties = [c for s, c in scored if s == best[0] and c["id"] != best[1]["id"]]
    res = {"status": "ok", "bv_nr": best[1]["id"], "url": f"https://gateway-bayern.de/{best[1]['id']}",
           "titel": best[1]["title"].strip(), "score": round(best[0], 2), "kandidaten": len(scored)}
    if ties:
        res["hinweis"] = f"{len(ties) + 1} gleich gute Treffer, erster gewaehlt"
    return res


def run(literature_path: Path, cache_path: Path) -> None:
    catalog = json.loads(literature_path.read_text(encoding="utf-8"))
    cache: dict = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = [e for e in catalog if e["slug"] not in cache and (e.get("gateway_bayern") or {}).get("status") != "ok"]
    print(f"{len(catalog)} Eintraege, {len(todo)} werden per Titel gesucht.", flush=True)
    for n, e in enumerate(todo, start=1):
        try:
            cache[e["slug"]] = search(e)
        except (requests.RequestException, ElementTree.ParseError) as exc:
            print(f"[{n}/{len(todo)}] {e['slug']}: Fehler ({exc})", flush=True)
            continue
        time.sleep(INTERVAL)
        if n % 50 == 0:
            print(f"[{n}/{len(todo)}] ...", flush=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    print("Fertig:", dict(Counter(v["status"] for v in cache.values())), flush=True)


def apply(literature_path: Path, cache_path: Path) -> None:
    catalog = json.loads(literature_path.read_text(encoding="utf-8"))
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    n = 0
    for e in catalog:
        m = cache.get(e["slug"])
        if m and m["status"] == "ok" and (e.get("gateway_bayern") or {}).get("status") != "ok":
            e["gateway_bayern"] = {"status": "ok", "bv_nr": m["bv_nr"], "url": m["url"], "isbn_used": None,
                                   "via": "titel", "titel": m.get("titel")}
            n += 1
    literature_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{n} Eintraege per Titelsuche mit Gateway Bayern verknuepft.")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    lit, cache = root / "site" / "src" / "data" / "literature.json", root / "etl" / "cache" / "gateway_titel_matches.json"
    if "--apply" in sys.argv:
        apply(lit, cache)
    else:
        run(lit, cache)
