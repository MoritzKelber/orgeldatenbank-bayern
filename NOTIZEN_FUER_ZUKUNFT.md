# Notizen für Zukunft

Ideen und offene Punkte, die nicht sofort umgesetzt werden, aber für später festgehalten werden sollen.

## To Do

- **QGIS-Visualisierung aufbauen.** QGIS (wissenschaftlicher Standard für GIS) als Analyse-Werkzeug
  neben der öffentlichen Leaflet-Karte nutzen - nicht als Ersatz dafür, da die Website bewusst statisch
  auf GitHub Pages läuft und QGIS Server/QGIS Cloud einen laufenden Server bräuchten. Sinnvoller Nutzen:
  - Echte räumliche Verschneidung (Punkt-in-Polygon) mit amtlichen Landkreis-/Gemeindegrenzen
    (ALKIS-Verwaltungsgebiete, geodaten.bayern.de) statt der bisherigen Näherung über die Distanz zum
    Landkreis-Mittelpunkt bei der Geocoding-Disambiguierung (siehe `etl/src/geocode/crosscheck_ortslage.py`).
  - Saubere Kartenexporte/Visualisierungen für Publikationen oder Präsentationen abseits der Website.
  - Datenqualitätsprüfung der `places.json`/`geocode_cache.json`-Koordinaten mit echten GIS-Werkzeugen.
