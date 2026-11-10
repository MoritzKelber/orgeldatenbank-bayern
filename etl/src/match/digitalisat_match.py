"""Find free digitised copies (Digitalisate) of literature entries at scholarly
providers and link them.

    cd etl/src
    <venv>/Scripts/python.exe match/digitalisat_match.py                 # search (cached)
    <venv>/Scripts/python.exe match/digitalisat_match.py --limit 40      # try a sample
    <venv>/Scripts/python.exe match/digitalisat_match.py --apply         # merge into literature.json

Two sources, both public and both restricted to libraries, archives, universities
and learned societies (no Google Books, no Internet Archive, no paywalled
publisher copies):

  * Deutsche Digitale Bibliothek (DDB), Solr API with fq=digitalisat:true.
    Aggregates the digitisations of the Bayerische Staatsbibliothek (MDZ),
    bavarikon, SLUB, university libraries etc. Journals are present volume by
    volume ("Zeitschrift fuer Instrumentenbau. 6. 1885"), so a journal article
    can be linked to the digitised volume it appeared in.
  * B3Kat SRU (bvbr.bib-bvb.de:5661/bvb01sru): electronic records / 856 fields
    marked "Volltext" and "kostenfrei" whose host is on the whitelist below.

Matching mirrors gateway_titel_match.py: title score >= 0.85, surname in the
persons, year +-1. The structure of each citation (journal name, volume, year)
comes from etl/cache/zitat_struktur.json, exported from site/src/lib/zitat.ts.

Result per slug in etl/cache/digitalisat_matches.json:
  {"status": "ok"|"keine", "links": [{"url", "anbieter", "beschreibung",
                                      "ebene": "titel"|"sammelband"|"band"|"zeitschrift",
                                      "quelle": "ddb"|"b3kat"}]}
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gateway_titel_match import _STOP, clean_title, fold, records, surnames, title_score, words  # noqa: E402

DDB_URL = "https://api.deutsche-digitale-bibliothek.de/2/search/index/search/select"
SRU_URL = "http://bvbr.bib-bvb.de:5661/bvb01sru"
USER_AGENT = "orgeldatenbank-bayern-digitalisat-matcher/1.0 (https://github.com/MoritzKelber/orgeldatenbank-bayern)"
INTERVAL = 0.4
DDB_FIELDS = "id,label,title,affiliate,provider_fct,view,begin_time,objecttype_fct,type_fct"

# Hosts of scholarly / public-sector providers whose digitisations we link.
ALLOW_HOSTS = (
    "digitale-sammlungen.de", "mdz-nbn-resolving.de", "bavarikon.de", "deutsche-digitale-bibliothek.de",
    "nbn-resolving.de", "nbn-resolving.org", "digizeitschriften.de", "slub-dresden.de", "staatsbibliothek-berlin.de",
    "sbb.berlin", "dilibri.de", "dfg-viewer.de", "digital.bib-bvb.de", "heimatforschung-regensburg.de", "zobodat.at",
    "e-periodica.ch", "e-rara.ch", "onb.ac.at", "hathitrust.org", "persee.fr", "gallica.bnf.fr", "europeana.eu",
    "oapen.org", "doabooks.org", "zenodo.org", "bsb-muenchen.de", "ulb-bonn.de", "ulb.tu-darmstadt.de", "tib.eu",
    "hab.de", "blb-karlsruhe.de", "wlb-stuttgart.de", "landesbibliothek.at", "digitale-bibliothek-mv.de",
    "digital.ub.uni-duesseldorf.de", "sammlungen.ub.uni-frankfurt.de",
)
ALLOW_PATTERNS = (
    re.compile(r"(^|\.)uni-[a-z-]+\.(de|at|ch)$"),           # Hochschulserver (ub., opus., epub., digital. ...)
    re.compile(r"(^|\.)(ub|ulb|lb|slub|sbb|hab|tu|th|fh)[.-][a-z-]+\.(de|at|ch)$"),
    re.compile(r"(^|\.)uni[a-z]+\.(de|at|ch)$"),             # unibe.ch, unileipzig? (selten)
    re.compile(r"(^|\.)(opus|epub|digital|digi|publikationen|journals|rep|edoc|docserv)\.[a-z0-9.-]+\.(de|at|ch)$"),
)
DENY_HOSTS = ("google.", "archive.org", "amazon.", "ebookcentral", "proquest", "ezb.ur.de", "dbis.", "zdb-katalog",
              "worldcat", "swb.bsz-bw.de", "d-nb.info", "deutsche-nationalbibliothek", "elibrary.utb", "utb.de",
              "nomos-elibrary", "beck-elibrary", "content-select", "ciando", "scribd", "academia.edu", "researchgate")


def unue(text: str) -> str:
    """'Ueber', 'Aebte', 'Oesterreich' -> 'Über', 'Äbte', 'Österreich' (the
    catalogues fold Ü to U, so a transcribed 'Ue' would never match)."""
    return re.sub(r"\b([UAO])e(?=[a-zäöüß])", lambda m: {"U": "Ü", "A": "Ä", "O": "Ö"}[m.group(1)], text)


def query_words(titel: str, n: int) -> list[str]:
    """Search words with umlauts kept: neither the DDB nor B3Kat fold 'ü' to
    'u', so the folded words of gateway_titel_match.words() would miss
    'Prüfung' or 'München'."""
    toks = re.findall(r"[^\W\d_]+", unue(clean_title(titel)).lower())
    return [w for w in toks if len(w) >= 3 and fold(w).strip() not in _STOP][:n]


def raw_surnames(autor: str | None) -> list[str]:
    """Like surnames(), but unfolded (for queries)."""
    if not autor or autor.strip().lower().startswith("anonym"):
        return []
    out = []
    for part in re.split(r"[/;]| und ", autor):
        s = re.sub(r"^(Hrsg\.|Hg\.)\s*", "", part.split(",")[0].strip())
        if len(s) >= 3:
            out.append(s.split()[-1].lower())
    return out


def title_match(ours: str, theirs: str, journal: bool = False) -> float:
    """title_score plus two relaxations for catalogue titles: old prints carry
    long baroque titles of which ours is only the beginning, and journal
    records carry subtitles ("Das Bayerland : älteste bayerische Zeitschrift
    ..."). Both are only accepted together with an author/year check."""
    ours, theirs = unue(ours), unue(theirs)
    theirs = re.split(r"\s[:;]\s", theirs, maxsplit=1)[0] if journal else theirs
    s = title_score(ours, theirs)
    if s >= 0.85:
        return s
    a, b = words(clean_title(ours)), words(clean_title(theirs))
    fa, fb = " ".join(a), " ".join(b)
    if not fa:
        return s
    if fb.startswith(fa) and (len(a) >= 3 or len(fa) >= 12 or (journal and len(fa) >= 8)):
        return 0.9
    if len(a) >= 3 and set(a) <= set(b):
        return 0.88
    return s


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host or any(d in host for d in DENY_HOSTS):
        return False
    if any(host == h or host.endswith("." + h) for h in ALLOW_HOSTS):
        return True
    return any(p.search(host) for p in ALLOW_PATTERNS)


def provider_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "digitale-sammlungen" in host or "mdz-nbn" in host or "bsb-muenchen" in host:
        return "Bayerische Staatsbibliothek (MDZ)"
    if "bavarikon" in host:
        return "bavarikon"
    if "digizeitschriften" in host:
        return "DigiZeitschriften"
    if "slub" in host:
        return "SLUB Dresden"
    if "heimatforschung-regensburg" in host:
        return "Historischer Verein für Oberpfalz und Regensburg"
    if "deutsche-digitale-bibliothek" in host:
        return "Deutsche Digitale Bibliothek"
    if "nbn-resolving" in host:
        return "URN-Resolver (DNB)"
    return host


def urn_to_url(urn: str) -> str:
    m = re.match(r"urn:nbn:de:bvb:12-(bsb\d+)-\d", urn)
    if m:
        return f"https://www.digitale-sammlungen.de/view/{m.group(1)}"
    return f"https://nbn-resolving.org/{urn}"


def get(url: str, attempt: int = 1) -> requests.Response:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=40)
        if r.status_code in (429, 500, 502, 503, 504):
            raise requests.RequestException(f"HTTP {r.status_code}")
        r.raise_for_status()
        return r
    except requests.RequestException:
        if attempt >= 4:
            raise
        time.sleep(3 * 2**attempt)
        return get(url, attempt + 1)


# --------------------------------------------------------------------------- DDB
def ddb_query(q: str, rows: int = 20) -> list[dict]:
    url = f"{DDB_URL}?q={quote(q)}&fq=digitalisat:true&wt=json&rows={rows}&fl={DDB_FIELDS}"
    data = get(url).json()
    return data.get("response", {}).get("docs", [])


def ddb_years(doc: dict) -> list[int]:
    ys = []
    for v in doc.get("view", []):
        ys += [int(y) for y in re.findall(r"\b(1[4-9]\d\d|20[0-2]\d)\b", v)] if len(v) <= 12 else []
    return ys


def ddb_link(doc: dict) -> tuple[str, str]:
    for v in doc.get("view", []):
        if v.startswith("urn:nbn:"):
            return urn_to_url(v), (doc.get("provider_fct") or ["Deutsche Digitale Bibliothek"])[0]
    return f"https://www.deutsche-digitale-bibliothek.de/item/{doc['id']}", (doc.get("provider_fct") or ["Deutsche Digitale Bibliothek"])[0]


def ddb_label(doc: dict) -> str:
    return (doc.get("label") or doc.get("title") or [""])[0]


def ddb_search_title(titel: str, names: list[str], year: int | None, ebene: str, qnames: list[str] | None = None) -> list[dict]:
    qnames = qnames if qnames is not None else names
    docs: list[dict] = []
    for n in (5, 3):
        ws = query_words(titel, n)
        if not ws or (n == 3 and not (names or year)):
            break
        q = "title:(" + " AND ".join(ws) + ")"
        if qnames:
            q += f" AND affiliate:{qnames[0]}"
        docs = ddb_query(q)
        if docs:
            break
        time.sleep(INTERVAL)
    out = []
    for doc in docs:
        if "Zeitschrift" in (doc.get("objecttype_fct") or []):
            continue
        label = re.sub(r"\.\s*\d+\.\s*\d{4}(/\d{2,4})?\s*$", "", ddb_label(doc))
        s = title_match(titel, label)
        if s < 0.85:
            continue
        if names and not any(n in fold(" ".join(doc.get("affiliate", []))) for n in names):
            continue
        ys = ddb_years(doc)
        if year is not None and ys and not any(abs(y - year) <= 1 for y in ys):
            continue
        if not names and year is None and s < 1.0:
            continue
        url, prov = ddb_link(doc)
        out.append({"url": url, "anbieter": prov, "beschreibung": ddb_label(doc), "ebene": ebene, "quelle": "ddb", "score": round(s, 2)})
    return out


VOL_RE = re.compile(r"^(?P<t>.+?)[.,;]?\s+(?:(?:Bd\.|Jg\.|Band|Jahrgang|Vol\.)\s*)?(?P<band>\d{1,3})\s*[.,]\s*(?P<jahr>\d{4})(?:/(?P<jahr2>\d{2,4}))?")
YEAR_RE = re.compile(r"^(?P<t>.+?)[.,;]?\s+(?P<jahr>1[5-9]\d\d|20[0-2]\d)(?:/(?P<jahr2>\d{2,4}))?\s*$")


def ddb_journal_volumes(container: str) -> list[dict]:
    """All digitised volumes of a journal in the DDB: [{band, jahre, url, anbieter, label}]."""
    phrase = clean_title(container).replace('"', "")
    docs = ddb_query(f'title:"{phrase}"', rows=400)
    vols = []
    for doc in docs:
        label = ddb_label(doc)
        m = VOL_RE.match(label) or YEAR_RE.match(label)
        if not m:
            continue
        if title_match(container, m.group("t"), journal=True) < 0.85:
            continue
        jahre = [int(m.group("jahr"))]
        if m.groupdict().get("jahr2"):
            j2 = m.group("jahr2")
            jahre.append(int(j2) if len(j2) == 4 else int(str(jahre[0])[: 4 - len(j2)] + j2))
        url, prov = ddb_link(doc)
        vols.append({"band": int(m.group("band")) if "band" in m.groupdict() and m.group("band") else None,
                     "jahre": jahre, "url": url, "anbieter": prov, "label": label})
    return vols


# ------------------------------------------------------------------------- B3Kat
def sru(query: str) -> ElementTree.Element:
    url = f"{SRU_URL}?version=1.1&operation=searchRetrieve&query={quote(query)}&maximumRecords=25&recordSchema=marcxml"
    return ElementTree.fromstring(get(url).content)


M = "{http://www.loc.gov/MARC21/slim}"


def b3kat_records(root: ElementTree.Element) -> list[dict]:
    """records() from gateway_titel_match plus 856 links and 007."""
    recs = records(root)
    xml_recs = list(root.iter(M + "record"))
    for d, rec in zip(recs, xml_recs):
        d["links"] = []
        d["f007"] = ""
        for cf in rec.findall(M + "controlfield"):
            if cf.get("tag") == "007" and not d["f007"]:
                d["f007"] = cf.text or ""
        for df in rec.findall(M + "datafield"):
            if df.get("tag") == "856":
                d["links"].append({sf.get("code"): (sf.text or "") for sf in df.findall(M + "subfield")})
    return recs


def good_links(rec: dict) -> list[dict]:
    out = []
    for l in rec["links"]:
        u, x, z, n3 = l.get("u", ""), l.get("x", ""), l.get("z", ""), l.get("3", "")
        if not u.startswith("http") or "Inhaltsverzeichnis" in n3 or "Klappentext" in n3 or "Rezension" in n3:
            continue
        if not host_allowed(u):
            continue
        free = "kostenfrei" in z.lower() or "open access" in z.lower() or "kostenlos" in z.lower()
        if x.lower().startswith("verlag") and not free:
            continue
        if not free and not any(k in n3.lower() for k in ("volltext", "digitalisat")) and "Digitalisierung" not in x:
            continue
        out.append({"url": u, "anbieter": provider_of(u), "hinweis": x})
    return out


def b3kat_search_title(titel: str, names: list[str], year: int | None, ebene: str, qnames: list[str] | None = None) -> list[dict]:
    qnames = qnames if qnames is not None else names
    recs: list[dict] = []
    for n in (4, 3):
        ws = query_words(titel, n)
        if not ws or (n == 3 and not (names or year)):
            break
        parts = [f"marcxml.title = {w}" for w in ws]
        if qnames:
            parts.append(f"marcxml.creator = {qnames[0]}")
        recs = b3kat_records(sru(" and ".join(parts)))
        if recs:
            break
        time.sleep(INTERVAL)
    out = []
    for rec in recs:
        if rec["leader"][6:7] not in ("a", "t") or rec["leader"][7:8] not in ("m", "a"):
            continue
        s = title_match(titel, rec["title"])
        if s < 0.85:
            continue
        if names and not any(n in fold(" ".join(rec["people"])) for n in names):
            continue
        if year is not None and rec["years"] and not any(abs(y - year) <= 1 for y in rec["years"]):
            continue
        if not names and year is None and s < 1.0:
            continue
        for l in good_links(rec):
            out.append({**l, "beschreibung": rec["title"].strip(), "ebene": ebene, "quelle": "b3kat", "score": round(s, 2), "bv_nr": rec["id"]})
    return out


RANGE_RE = re.compile(r"(\d{4})\s*(?:-|–|bis)\s*(\d{4})?")


def b3kat_journal(container: str) -> list[dict]:
    """Digitised journal (whole run or year range) in B3Kat: [{url, anbieter, von, bis, hinweis}]."""
    ws = query_words(container, 4)
    if not ws:
        return []
    out = []
    for rec in b3kat_records(sru(" and ".join(f"marcxml.title = {w}" for w in ws))):
        if rec["leader"][7:8] != "s":
            continue
        if title_match(container, rec["title"], journal=True) < 0.85:
            continue
        von = bis = None
        for y in rec["years"]:
            von = y if von is None else min(von, y)
            bis = y if bis is None else max(bis, y)
        for l in good_links(rec):
            lv, lb = von, bis
            m = RANGE_RE.search(l["hinweis"])
            if m:
                lv = int(m.group(1))
                lb = int(m.group(2)) if m.group(2) else lb
            out.append({**l, "von": lv, "bis": lb, "beschreibung": rec["title"].strip(), "bv_nr": rec["id"]})
    return out


# -------------------------------------------------------------------------- run
def dedupe(links: list[dict]) -> list[dict]:
    seen, out = set(), []
    # DDB/MDZ viewer links first, the mdz-nbn-resolving form of the same copy is dropped.
    links = sorted(links, key=lambda l: "nbn-resolving" in l["url"])
    for l in links:
        m = re.search(r"(bsb\d{8})", l["url"])
        key = m.group(1) if m else re.sub(r"^https?://(www\.)?", "", l["url"]).rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append({k: v for k, v in l.items() if k not in ("hinweis",)})
    return out


def search_entry(entry: dict, z: dict, jcache: dict) -> dict:
    links: list[dict] = []
    year = z.get("jahr")
    titel = entry.get("titel") or ""
    if titel.lower().startswith(("rez", "rezension")):
        return {"status": "keine"}
    art = z.get("art")
    if art == "zeitschrift" and z.get("container"):
        c = z["container"]
        if c not in jcache:
            jcache[c] = {"ddb": ddb_journal_volumes(c), "b3kat": b3kat_journal(c)}
            time.sleep(INTERVAL)
        band = z.get("band")
        hits = [v for v in jcache[c]["ddb"] if (band and v["band"] == band) or (year and year in v["jahre"])]
        hits.sort(key=lambda v: -((band is not None and v["band"] == band) + (year in v["jahre"] if year else 0)))
        for v in hits[:2]:
            links.append({"url": v["url"], "anbieter": v["anbieter"], "beschreibung": v["label"], "ebene": "band", "quelle": "ddb"})
        if not links and year:
            for j in jcache[c]["b3kat"]:
                if (j["von"] is None or j["von"] <= year) and (j["bis"] is None or year <= j["bis"]):
                    links.append({"url": j["url"], "anbieter": j["anbieter"], "ebene": "zeitschrift", "quelle": "b3kat",
                                  "beschreibung": j["beschreibung"] + (f" ({j['von']}–{j['bis']})" if j["von"] and j["bis"] else "")})
    elif art == "sammelband" and z.get("container"):
        c = z["container"]
        links += ddb_search_title(c, [], year, "sammelband")
        time.sleep(INTERVAL)
        links += b3kat_search_title(c, [], year, "sammelband")
    elif titel:
        names, qnames = surnames(entry.get("autor")), raw_surnames(entry.get("autor"))
        links += ddb_search_title(titel, names, year, "titel", qnames)
        time.sleep(INTERVAL)
        links += b3kat_search_title(titel, names, year, "titel", qnames)
    links = dedupe(links)
    zs = [l for l in links if l["ebene"] == "zeitschrift"][:1]  # ein Zugang je Zeitschrift
    links = ([l for l in links if l["ebene"] != "zeitschrift"] + zs)[:3]
    return {"status": "ok", "links": links} if links else {"status": "keine"}


def run(root: Path, limit: int | None) -> None:
    lit_path = root / "site" / "src" / "data" / "literature.json"
    cache_path = root / "etl" / "cache" / "digitalisat_matches.json"
    jcache_path = root / "etl" / "cache" / "digitalisat_zeitschriften.json"
    struct = json.loads((root / "etl" / "cache" / "zitat_struktur.json").read_text(encoding="utf-8"))
    catalog = json.loads(lit_path.read_text(encoding="utf-8"))
    cache: dict = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    jcache: dict = json.loads(jcache_path.read_text(encoding="utf-8")) if jcache_path.exists() else {}
    todo = [e for e in catalog if e["slug"] not in cache]
    if "--slugs" in sys.argv:
        wanted = set(sys.argv[sys.argv.index("--slugs") + 1].split(","))
        todo = [e for e in catalog if e["slug"] in wanted]
    if limit:
        todo = todo[:limit]
    print(f"{len(catalog)} Eintraege, {len(todo)} werden gesucht.", flush=True)

    def save() -> None:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        jcache_path.write_text(json.dumps(jcache, ensure_ascii=False, indent=1), encoding="utf-8")

    for n, e in enumerate(todo, start=1):
        try:
            cache[e["slug"]] = search_entry(e, struct.get(e["slug"], {}), jcache)
        except (requests.RequestException, ElementTree.ParseError, ValueError) as exc:
            print(f"[{n}/{len(todo)}] {e['slug']}: Fehler ({exc})", flush=True)
            continue
        if cache[e["slug"]]["status"] == "ok":
            print(f"[{n}/{len(todo)}] {e['slug']}: {cache[e['slug']]['links'][0]['url']}", flush=True)
        time.sleep(INTERVAL)
        if n % 25 == 0:
            print(f"[{n}/{len(todo)}] ...", flush=True)
            save()
    save()
    from collections import Counter
    print("Fertig:", dict(Counter(v["status"] for v in cache.values())), flush=True)


# DDB also aggregates photo archives, museums and archive records (charters);
# those are pictures of the same church or documents, not copies of the cited
# publication. Only libraries and universities count as scholarly providers.
BAD_PROVIDER = ("foto", "bildarchiv", "dia-archiv", "museum", "archiv", "deutsche digitale bibliothek",
                "deutsche nationalbibliothek")


def provider_ok(anbieter: str) -> bool:
    a = anbieter.lower()
    return not any(b in a for b in BAD_PROVIDER) or "staatsbibliothek" in a or "landesbibliothek" in a


def apply(root: Path) -> None:
    lit_path = root / "site" / "src" / "data" / "literature.json"
    cache = json.loads((root / "etl" / "cache" / "digitalisat_matches.json").read_text(encoding="utf-8"))
    catalog = json.loads(lit_path.read_text(encoding="utf-8"))
    n = 0
    for e in catalog:
        m = cache.get(e["slug"])
        links = [l for l in (m or {}).get("links", []) if provider_ok(l["anbieter"])]
        if links:
            e["digitalisat"] = {"status": "ok", "links": [{k: v for k, v in l.items() if k != "score"} for l in links]}
            n += 1
        else:
            e["digitalisat"] = None
    lit_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{n} Eintraege mit Digitalisat verknuepft.")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    if "--apply" in sys.argv:
        apply(root)
    else:
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        run(root, lim)
