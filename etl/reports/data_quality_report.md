# Datenqualitäts-Report — bayern.accdb

Generiert: 2026-11-04

## Zeilenzahlen (Quelle vs. verarbeitet)

| Tabelle | Quelle | Verarbeitet |
|---|---|---|
| Bydaten (Orgeln) | 32262 | 32262 |
| Bybauer (Erbauer) | 1000 | 1000 |
| Byliteratur (Katalog) | 2419 | 2417 |
| Literatur (Zitate) | 69957 | 69957 |

## JAHR — Bereinigung

| Qualifier | Anzahl | Anteil |
|---|---|---|
| exakt | 22919 | 71.0% |
| fehlt | 3244 | 10.1% |
| vor | 2898 | 9.0% |
| um | 1845 | 5.7% |
| bereich | 771 | 2.4% |
| nach | 571 | 1.8% |
| unbekannt | 14 | 0.0% |

Beispiele für nicht einordenbare JAHR-Rohwerte (Review empfohlen):
'195?=', '1922?', '1982=,', '1962?', '1955=,', '19282<', '?', '?', '1749?', '?', '1867<?', '18??', '1914?', '2003?'

## DISPO — Parse-Abdeckung

- Orgeln mit DISPO-Text: 10905 von 32262 (33.8%)
- Davon als Registersektionen strukturiert erkannt (>=2 Sections): 10610 (97.3%)
- Nicht zuordenbare Zeilen insgesamt (in extra_notes, kein Datenverlust): 425

## BAUER — Zuordnung zur Erbauer-Lexikon (Bybauer)

- Orgeln mit BAUER-Text: 22278 von 32262
- Davon mit sicherer Verknüpfung zu einem Bybauer-Eintrag: 116 (0.5%) — erwartungsgemäß niedrig, siehe Hinweis im Plan: Bybauer ist ein eigenständiges Lexikon von ca. 1.000 Erbauern, kein vollständiges Register zu allen 2.700+ in Bydaten.BAUER vorkommenden Namen.

## LITERATUR — Abgleich Literatur.LIT ↔ Byliteratur.KURZTITEL

| Konfidenz | Anzahl | Anteil |
|---|---|---|
| normalisiert | 52160 | 74.6% |
| keine | 14463 | 20.7% |
| exact | 3008 | 4.3% |
| fuzzy | 326 | 0.5% |

'keine' bedeutet überwiegend echte Lücken im Katalog (z.B. persönliche Mitteilungen, nie in Byliteratur nacherfasst) - das Zitat wird trotzdem immer als Text angezeigt, nur ohne Verlinkung.

## LANDKREIS — Abgleich gegen Bylkr

Landkreis-Werte in Bydaten, die nicht in Bylkr vorkommen:
- 'Erlangen-Höchstädt': 7 Orgeln
- 'Neustadt/Waldnaab': 1 Orgeln

## GEOCODING — Umfang (für Milestone 4)

- Distinkte Orts-Schlüssel (place_key): 8839
- Orgeln ohne verwertbaren Orts-Schlüssel: 186

## REGIERUNGSBEZIRK (RBZ) — Normalisierung

RBZ-Rohwerte, die nicht auf einen der 7 bayerischen Regierungsbezirke passen (fallen in den 'unbekannt'-Shard, Rohwert bleibt in _unclear erhalten):
- 'LB': 1 Orgel(n)

## Offen/ausgeblendet gehaltene Felder (DP, KL, T, SATZ)

T-Werte: 'N': 19206, 'R': 6040, None: 4114, 'U': 2898, '?': 2, 'E': 1, 'e': 1

KL-Werte: 'kP': 14219, 'eK': 6219, 'kK': 5072, 'kF': 4201, None: 2527, 'eF': 19, 'e': 4, 'ek': 1
