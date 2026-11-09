"""ETL entrypoint: bayern.accdb -> cleaned JSON for the Astro site.

Run locally on Windows (the Access ODBC driver is Windows-only), from
inside etl/src/ so the sibling `sources`/`transform` packages resolve:

    cd etl/src
    <path-to-venv>/Scripts/python.exe pipeline.py --db "<path to bayern.accdb>"

See etl/README.md for the full setup.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from sources.access_source import fetch_source
from transform.bauer_match import build_lookup as build_bauer_lookup
from transform.clean_bybauer import clean_bybauer_row
from transform.clean_bydaten import clean_bydaten_row
from transform.clean_literatur import build_literature_catalog, build_organ_literature
from transform.jahr import format_jahr
from validate import build_report


def _rbz_shard_key(rbz: str | None) -> str:
    # rbz is already normalized to one of Bavaria's 7 canonical codes (or
    # None) by clean_bydaten_row - this just picks the shard bucket name.
    return rbz if rbz else "unbekannt"


def run(db_path: str, site_data_dir: Path, public_data_dir: Path, reports_dir: Path) -> None:
    print(f"Lese Rohdaten aus {db_path} ...")
    source = fetch_source(db_path)
    source_counts = {table: len(rows) for table, rows in source.items()}
    for table, n in source_counts.items():
        print(f"  {table}: {n} Zeilen")

    bauer_lookup = build_bauer_lookup(source["Bybauer"])

    jahr_overrides_path = Path(__file__).resolve().parents[1] / "cache" / "jahr_overrides.json"
    jahr_overrides = json.loads(jahr_overrides_path.read_text(encoding="utf-8")) if jahr_overrides_path.exists() else {}

    print("Bereinige Orgeln (Bydaten) ...")
    organs = [clean_bydaten_row(row, bauer_lookup, jahr_overrides) for row in source["Bydaten"]]

    print("Bereinige Erbauer (Bybauer) ...")
    builders = [clean_bybauer_row(row) for row in source["Bybauer"]]
    builders_by_id = {b["id"]: b for b in builders}

    print("Baue Literaturkatalog + Zitate ...")
    literature_catalog = build_literature_catalog(source["Byliteratur"], source["Bystichworte"])
    organ_literature = build_organ_literature(source["Literatur"], literature_catalog)

    for organ in organs:
        organ["literatur"] = organ_literature.get(organ["id"], [])
        if organ["bauer_confidence"] == "exact" and organ["bauer_id"] in builders_by_id:
            builders_by_id[organ["bauer_id"]]["organ_ids"].append(organ["id"])

    print("Schreibe JSON-Ausgaben ...")
    site_data_dir.mkdir(parents=True, exist_ok=True)
    organs_dir = site_data_dir / "organs"
    organs_dir.mkdir(exist_ok=True)

    shards: dict[str, list[dict]] = defaultdict(list)
    for organ in organs:
        shards[_rbz_shard_key(organ["regierungsbezirk"])].append(organ)
    for shard_key, shard_organs in shards.items():
        out_path = organs_dir / f"organs-{shard_key.lower()}.json"
        out_path.write_text(json.dumps(shard_organs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {out_path.name}: {len(shard_organs)} Orgeln")

    # Row-of-arrays instead of array-of-objects: with ~32k rows, repeating
    # 13 field-name strings in every object roughly doubles both the
    # download size and JSON.parse time for no benefit, since the client
    # (orgeln/index.astro) just needs the values - it indexes by the
    # fixed column order below instead of reconstructing objects. This
    # was a measured fix: Lighthouse flagged Total Blocking Time on
    # /orgeln/ before this change.
    index_fields = (
        "id", "ort", "kirche", "gemeinde", "landkreis", "regierungsbezirk",
        "bauer_name", "manuale", "register", "erhalten", "denkmalorgel", "prospekt_erhalten",
    )
    organs_index_rows = []
    for organ in organs:
        row = [organ[k] for k in index_fields]
        row.append(organ["jahr"]["jahr"])
        row.append(format_jahr(organ["jahr"]))
        organs_index_rows.append(row)
    # Goes to public/, not src/data/: this is the one file the browser
    # fetches at runtime for client-side filtering on /orgeln/ - the
    # per-organ shards above stay build-time-only (used to generate the
    # 32k static detail pages, never shipped raw to the client).
    public_data_dir.mkdir(parents=True, exist_ok=True)
    (public_data_dir / "organs-index.json").write_text(
        json.dumps(
            {"fields": [*index_fields, "jahr", "jahr_anzeige"], "rows": organs_index_rows},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    (site_data_dir / "builders.json").write_text(
        json.dumps(builders, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (site_data_dir / "literature.json").write_text(
        json.dumps(list(literature_catalog.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Union with the Landkreis values actually used in Bydaten: Bylkr is
    # missing a couple of real values ("Erlangen-Höchstädt",
    # "Neustadt/Waldnaab" - see data_quality_report.md), so using Bylkr
    # alone would silently drop real districts from a filter dropdown.
    lkr_from_lookup = {row["LKR"].strip() for row in source["Bylkr"] if row.get("LKR")}
    lkr_from_organs = {organ["landkreis"] for organ in organs if organ["landkreis"]}
    (site_data_dir / "lkr.json").write_text(
        json.dumps(sorted(lkr_from_lookup | lkr_from_organs), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Schreibe Datenqualitäts-Report ...")
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        organs=organs,
        builders=builders,
        literature_catalog=literature_catalog,
        organ_literature=organ_literature,
        bylkr_rows=source["Bylkr"],
        source_counts=source_counts,
    )
    (reports_dir / "data_quality_report.md").write_text(report, encoding="utf-8")
    print("Fertig.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL: bayern.accdb -> site JSON")
    parser.add_argument("--db", required=True, help="Pfad zur bayern.accdb")
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--site-data",
        default=str(repo_root / "site" / "src" / "data"),
        help="Zielverzeichnis für die build-time-JSON-Ausgaben (Detailseiten-Quelldaten)",
    )
    parser.add_argument(
        "--public-data",
        default=str(repo_root / "site" / "public" / "data"),
        help="Zielverzeichnis für Daten, die der Browser zur Laufzeit fetcht (organs-index.json)",
    )
    parser.add_argument(
        "--reports",
        default=str(Path(__file__).resolve().parents[1] / "reports"),
        help="Zielverzeichnis für den Datenqualitäts-Report",
    )
    args = parser.parse_args()
    run(args.db, Path(args.site_data), Path(args.public_data), Path(args.reports))


if __name__ == "__main__":
    main()
