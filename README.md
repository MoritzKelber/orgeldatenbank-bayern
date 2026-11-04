# Orgeldatenbank Bayern

Moderne, öffentliche Such-/Browsing-Website für eine seit über 20 Jahren
gepflegte Datenbank historischer Orgeln in Bayern (32.262 Instrumente).

Siehe [`etl/README.md`](etl/README.md) für die Datenpipeline und den
Umsetzungsplan im Projektverlauf für Architektur/Milestones.

## Stand

- **M1 — ETL + Validierung**: fertig. `bayern.accdb` → `site/src/data/*.json`,
  siehe `etl/reports/data_quality_report.md` für die Datenqualitätszahlen.
- **M2–M5**: noch offen (Astro-Site, Volltextsuche, Karte, Politur).

## Struktur

- `etl/` — Python-Pipeline, liest `bayern.accdb`, schreibt bereinigte JSON-Daten
- `site/` — Astro-Website (folgt in M2)
