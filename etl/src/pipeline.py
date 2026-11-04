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
from validate import build_report


def _rbz_shard_key(rbz: str | None) -> str:
    # rbz is already normalized to one of Bavaria's 7 canonical codes (or
    # None) by clean_bydaten_row - this just picks the shard bucket name.
    return rbz if rbz else "unbekannt"


def run(db_path: str, site_data_dir: Path, reports_dir: Path) -> None:
    print(f"Lese Rohdaten aus {db_path} ...")
    source = fetch_source(db_path)
    source_counts = {table: len(rows) for table, rows in source.items()}
    for table, n in source_counts.items():
        print(f"  {table}: {n} Zeilen")

    bauer_lookup = build_bauer_lookup(source["Bybauer"])

    print("Bereinige Orgeln (Bydaten) ...")
    organs = [clean_bydaten_row(row, bauer_lookup) for row in source["Bydaten"]]

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

    index_fields = (
        "id", "ort", "kirche", "gemeinde", "landkreis", "regierungsbezirk",
        "bauer_name", "manuale", "register", "erhalten", "denkmalorgel",
    )
    organs_index = []
    for organ in organs:
        entry = {k: organ[k] for k in index_fields}
        entry["jahr"] = organ["jahr"]["jahr"]
        entry["jahr_anzeige"] = _jahr_display(organ["jahr"])
        organs_index.append(entry)
    (site_data_dir / "organs-index.json").write_text(
        json.dumps(organs_index, ensure_ascii=False, indent=2), encoding="utf-8"
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


def _jahr_display(jahr: dict) -> str | None:
    if jahr["qualifier"] == "fehlt":
        return None
    if jahr["qualifier"] == "unbekannt":
        return jahr["jahr_raw"]
    if jahr["qualifier"] == "exakt":
        return str(jahr["jahr"])
    if jahr["qualifier"] == "vor":
        return f"vor {jahr['jahr']}"
    if jahr["qualifier"] == "nach":
        return f"nach {jahr['jahr']}"
    if jahr["qualifier"] == "um":
        return f"um {jahr['jahr']}"
    if jahr["qualifier"] == "bereich":
        return f"{jahr['jahr']}–{jahr['jahr_bis']}"
    return jahr["jahr_raw"]


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL: bayern.accdb -> site JSON")
    parser.add_argument("--db", required=True, help="Pfad zur bayern.accdb")
    parser.add_argument(
        "--site-data",
        default=str(Path(__file__).resolve().parents[2] / "site" / "src" / "data"),
        help="Zielverzeichnis für die JSON-Ausgaben",
    )
    parser.add_argument(
        "--reports",
        default=str(Path(__file__).resolve().parents[1] / "reports"),
        help="Zielverzeichnis für den Datenqualitäts-Report",
    )
    args = parser.parse_args()
    run(args.db, Path(args.site_data), Path(args.reports))


if __name__ == "__main__":
    main()
