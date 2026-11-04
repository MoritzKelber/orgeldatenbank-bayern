# ETL — bayern.accdb → site/src/data/*.json

Liest die Orgeldatenbank (`bayern.accdb`) per ODBC aus und erzeugt die
bereinigten JSON-Dateien, die die Astro-Website (`/site`) konsumiert.
Läuft **nur lokal unter Windows**, nicht in GitHub Actions — der
Microsoft Access ODBC-Treiber gibt es nicht für Linux-Runner.

## Einmaliges Setup

Der Access-ODBC-Treiber (64-bit, "Microsoft Access Driver (*.mdb, *.accdb)")
muss installiert sein — unter Windows mit Office i.d.R. schon vorhanden,
sonst: [Microsoft Access Database Engine 2016 Redistributable](https://www.microsoft.com/download/details.aspx?id=54920).

Die Python-Virtualenv liegt **bewusst außerhalb** dieses Dropbox-Ordners
(Dropbox sperrt Dateien während der Synchronisierung, was `pip install`
zum Absturz bringt):

```powershell
python -m venv C:\Users\<du>\.venvs\orgeldatenbank-etl
C:\Users\<du>\.venvs\orgeldatenbank-etl\Scripts\pip install -r etl\requirements.txt
```

## Ausführen

```powershell
cd etl\src
C:\Users\<du>\.venvs\orgeldatenbank-etl\Scripts\python.exe pipeline.py --db "<Pfad zu bayern.accdb>"
```

Schreibt:
- `site/src/data/organs/organs-<rbz>.json` — Orgeln, sortiert nach Regierungsbezirk
- `site/src/data/organs-index.json` — schlanke Felder fürs Such-/Filter-UI
- `site/src/data/builders.json`, `literature.json`, `lkr.json`
- `etl/reports/data_quality_report.md` — **vor jedem Site-Schritt lesen**

## Struktur

- `sources/access_source.py` — reine Rohextraktion (SELECT *), kein Cleaning
- `transform/` — ein Modul pro Bereinigungsschritt (siehe Docstrings für
  die realen Datenmuster, gegen die jeweils getestet wurde)
- `validate.py` — baut den Datenqualitäts-Report
- `pipeline.py` — Einstiegspunkt, orchestriert alles

## Bekannte offene Punkte (siehe Report für aktuelle Zahlen)

- **DP, KL, T, SATZ**: Bedeutung unklar (außer DO = Denkmalorgel, bereits
  umgesetzt). Werte bleiben pro Orgel in `_unclear` erhalten, werden aber
  nicht angezeigt, bis geklärt.
- **BAUER → Bybauer-Verknüpfung**: nur ~0,5% der Orgeln lassen sich sicher
  einem Bybauer-Lexikoneintrag zuordnen (siehe Report) — erwartet, kein Bug.
  Bybauer ist ein eigenständiges Lexikon, kein vollständiges Register.
- **Literatur-Zitate ohne Katalogeintrag** (~21%): meist echte Lücken
  (persönliche Mitteilungen etc.), werden als Text ohne Link angezeigt.
