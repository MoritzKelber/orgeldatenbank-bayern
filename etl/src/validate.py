"""Generate etl/reports/data_quality_report.md from the cleaned data.

This is the review artifact for Milestone 1 - read it before any site
code gets written, per the plan.
"""
from __future__ import annotations

from collections import Counter
from datetime import date


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{n / total * 100:.1f}%"


def build_report(
    *,
    organs: list[dict],
    builders: list[dict],
    literature_catalog: dict[str, dict],
    organ_literature: dict[int, list[dict]],
    bylkr_rows: list[dict],
    source_counts: dict[str, int],
) -> str:
    total_organs = len(organs)
    lines: list[str] = []
    lines.append(f"# Datenqualitäts-Report — bayern.accdb\n")
    lines.append(f"Generiert: {date.today().isoformat()}\n")

    lines.append("## Zeilenzahlen (Quelle vs. verarbeitet)\n")
    lines.append("| Tabelle | Quelle | Verarbeitet |")
    lines.append("|---|---|---|")
    lines.append(f"| Bydaten (Orgeln) | {source_counts.get('Bydaten')} | {total_organs} |")
    lines.append(f"| Bybauer (Erbauer) | {source_counts.get('Bybauer')} | {len(builders)} |")
    lines.append(f"| Byliteratur (Katalog) | {source_counts.get('Byliteratur')} | {len(literature_catalog)} |")
    lines.append(f"| Literatur (Zitate) | {source_counts.get('Literatur')} | {sum(len(v) for v in organ_literature.values())} |")
    lines.append("")

    lines.append("## JAHR — Bereinigung\n")
    qualifier_counts = Counter(o["jahr"]["qualifier"] for o in organs)
    lines.append("| Qualifier | Anzahl | Anteil |")
    lines.append("|---|---|---|")
    for qualifier, n in qualifier_counts.most_common():
        lines.append(f"| {qualifier} | {n} | {_pct(n, total_organs)} |")
    unbekannt_samples = [o["jahr"]["jahr_raw"] for o in organs if o["jahr"]["qualifier"] == "unbekannt"][:20]
    if unbekannt_samples:
        lines.append("\nBeispiele für nicht einordenbare JAHR-Rohwerte (Review empfohlen):")
        lines.append(", ".join(repr(s) for s in unbekannt_samples))
    lines.append("")

    lines.append("## DISPO — Parse-Abdeckung\n")
    with_dispo = [o for o in organs if o["dispo"]["raw"]]
    parsed_ok = [o for o in with_dispo if o["dispo"]["parsed"]]
    lines.append(f"- Orgeln mit DISPO-Text: {len(with_dispo)} von {total_organs} ({_pct(len(with_dispo), total_organs)})")
    lines.append(
        f"- Davon als Registersektionen strukturiert erkannt (>=2 Sections): {len(parsed_ok)} "
        f"({_pct(len(parsed_ok), len(with_dispo))})"
    )
    extra_notes_total = sum(len(o["dispo"]["extra_notes"]) for o in with_dispo)
    lines.append(f"- Nicht zuordenbare Zeilen insgesamt (in extra_notes, kein Datenverlust): {extra_notes_total}")
    lines.append("")

    lines.append("## BAUER — Zuordnung zur Erbauer-Lexikon (Bybauer)\n")
    with_bauer = [o for o in organs if o["bauer_name"]]
    confident = [o for o in with_bauer if o["bauer_confidence"] == "exact"]
    lines.append(f"- Orgeln mit BAUER-Text: {len(with_bauer)} von {total_organs}")
    lines.append(
        f"- Davon mit sicherer Verknüpfung zu einem Bybauer-Eintrag: {len(confident)} "
        f"({_pct(len(confident), len(with_bauer))}) — erwartungsgemäß niedrig, siehe Hinweis im Plan: "
        "Bybauer ist ein eigenständiges Lexikon von ca. 1.000 Erbauern, kein vollständiges Register "
        "zu allen 2.700+ in Bydaten.BAUER vorkommenden Namen."
    )
    lines.append("")

    lines.append("## LITERATUR — Abgleich Literatur.LIT ↔ Byliteratur.KURZTITEL\n")
    all_citations = [c for citations in organ_literature.values() for c in citations]
    confidence_counts = Counter(c["confidence"] for c in all_citations)
    lines.append("| Konfidenz | Anzahl | Anteil |")
    lines.append("|---|---|---|")
    for confidence, n in confidence_counts.most_common():
        lines.append(f"| {confidence} | {n} | {_pct(n, len(all_citations))} |")
    lines.append(
        "\n'keine' bedeutet überwiegend echte Lücken im Katalog (z.B. persönliche Mitteilungen, "
        "nie in Byliteratur nacherfasst) - das Zitat wird trotzdem immer als Text angezeigt, nur "
        "ohne Verlinkung."
    )
    lines.append("")

    lines.append("## LANDKREIS — Abgleich gegen Bylkr\n")
    known_lkr = {row["LKR"].strip() for row in bylkr_rows if row.get("LKR")}
    used_lkr = Counter(o["landkreis"] for o in organs if o["landkreis"])
    orphans = {lkr: n for lkr, n in used_lkr.items() if lkr not in known_lkr}
    if orphans:
        lines.append("Landkreis-Werte in Bydaten, die nicht in Bylkr vorkommen:")
        for lkr, n in sorted(orphans.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {lkr!r}: {n} Orgeln")
    else:
        lines.append("Keine Ausreißer - alle LKR-Werte in Bydaten kommen auch in Bylkr vor.")
    lines.append("")

    lines.append("## GEOCODING — Umfang (für Milestone 4)\n")
    place_keys = {o["place_key"] for o in organs if o["place_key"]}
    without_place_key = sum(1 for o in organs if not o["place_key"])
    lines.append(f"- Distinkte Orts-Schlüssel (place_key): {len(place_keys)}")
    lines.append(f"- Orgeln ohne verwertbaren Orts-Schlüssel: {without_place_key}")
    lines.append("")

    lines.append("## REGIERUNGSBEZIRK (RBZ) — Normalisierung\n")
    unrecognized_rbz = Counter(
        o["_unclear"]["rbz_raw_unrecognized"] for o in organs if o["_unclear"]["rbz_raw_unrecognized"]
    )
    if unrecognized_rbz:
        lines.append(
            "RBZ-Rohwerte, die nicht auf einen der 7 bayerischen Regierungsbezirke "
            "passen (fallen in den 'unbekannt'-Shard, Rohwert bleibt in _unclear erhalten):"
        )
        for raw, n in unrecognized_rbz.most_common():
            lines.append(f"- {raw!r}: {n} Orgel(n)")
    else:
        lines.append("Keine Ausreißer.")
    lines.append("")

    lines.append("## Offen/ausgeblendet gehaltene Felder (DP, KL, T, SATZ)\n")
    t_counts = Counter(o["_unclear"]["t"] for o in organs)
    kl_counts = Counter(o["_unclear"]["kl"] for o in organs)
    lines.append("T-Werte: " + ", ".join(f"{k!r}: {n}" for k, n in t_counts.most_common()))
    lines.append("")
    lines.append("KL-Werte: " + ", ".join(f"{k!r}: {n}" for k, n in kl_counts.most_common()))
    lines.append("")

    return "\n".join(lines)
