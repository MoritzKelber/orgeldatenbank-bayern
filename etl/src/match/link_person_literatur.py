"""Link the "Lit.:" lines of the builder biographies to the literature catalog.

    cd etl/src
    <venv>/Scripts/python.exe match/link_person_literatur.py

The Erbauer biographies (builders.json, field `biografie`) end in lines like

    Lit.: Brenninger, Altbayern (1982), S.58
          Kraus, Oberpfalz (1990), S.74

which are the same short citations the organs use. Until now they were only
shown as plain text; this matches every line with
transform/literatur_match.match_literatur and writes both sides of the link:

  builders.json     lemma["literatur"] = [{"text", "slug"}]   (slug null = no catalog entry,
                                                                e.g. "Mitteilung ...", shown as text)
  literature.json   entry["lemma_ids"] = [lemma ids citing it]

Idempotent: both fields are rebuilt from scratch on every run.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transform.literatur_match import build_lookup, match_literatur  # noqa: E402

_LIT_BLOCK = re.compile(
    r"(?im)^[ \t]*Lit(?:eratur)?\.?[ \t]*:[ \t]*(.*(?:\n(?![ \t]*\n)(?![ \t]*[A-ZÄÖÜ][a-zäöü]+:).*)*)"
)
_LEAD = re.compile(r"^(?:\d+\.\s*|u\.\s*a\.\s*|vgl\.\s*|siehe\s+)", re.IGNORECASE)
_TRAIL_PAREN = re.compile(r"\s*\([^()]*\)\s*$")


def _items(block: str) -> list[str]:
    """Citations of one Lit: block. One per line; a line may hold several
    separated by ';' (a piece that does not start with a letter is just the
    rest of a page list, e.g. 'S.12; 15')."""
    out: list[str] = []
    for line in block.split("\n"):
        for piece in line.split(";"):
            piece = piece.strip().rstrip(".").strip() if piece.strip().endswith("..") else piece.strip()
            if not piece:
                continue
            if out and not re.match(r"[A-Za-zÄÖÜäöü]", piece):
                out[-1] += "; " + piece
            else:
                out.append(piece)
    return out


def _match(text: str, ks: set[str], kl: list[str]) -> dict:
    cand = _LEAD.sub("", text).strip()
    for attempt in (cand, _TRAIL_PAREN.sub("", cand)):
        m = match_literatur(attempt, ks, kl)
        if m["kurztitel"]:
            return m
    return {"kurztitel": None, "confidence": "keine"}


def main() -> None:
    data = Path(__file__).resolve().parents[3] / "site" / "src" / "data"
    builders = json.loads((data / "builders.json").read_text(encoding="utf-8"))
    catalog = json.loads((data / "literature.json").read_text(encoding="utf-8"))
    by_kt = {e["kurztitel"].strip(): e for e in catalog if e.get("kurztitel")}
    ks, kl = build_lookup([{"KURZTITEL": k} for k in by_kt])

    cited: dict[str, set[int]] = {}
    stats: Counter = Counter()
    for b in builders:
        refs, seen = [], set()
        for block in _LIT_BLOCK.finditer((b.get("biografie") or "").replace("\r\n", "\n")):
            for text in _items(block.group(1)):
                m = _match(text, ks, kl)
                slug = by_kt[m["kurztitel"]]["slug"] if m["kurztitel"] else None
                if (text, slug) in seen:
                    continue
                seen.add((text, slug))
                refs.append({"text": text, "slug": slug})
                stats["verknüpft" if slug else "ohne Katalogeintrag"] += 1
                if slug:
                    cited.setdefault(slug, set()).add(b["id"])
        b["literatur"] = refs

    for e in catalog:
        e["lemma_ids"] = sorted(cited.get(e["slug"], ()))

    (data / "builders.json").write_text(json.dumps(builders, ensure_ascii=False, indent=2), encoding="utf-8")
    (data / "literature.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    withlit = sum(1 for b in builders if b["literatur"])
    print(f"{dict(stats)}; {withlit} von {len(builders)} Lemmata mit Literatur, {len(cited)} Literatureinträge zitiert.")
    orphan = [e for e in catalog if not e["organ_ids"] and not e["lemma_ids"]]
    print(f"{len(orphan)} Literatureinträge weder bei Orgeln noch bei Personen zitiert.")


if __name__ == "__main__":
    main()
