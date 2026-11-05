"""Cross-check Nominatim results against the Bavarian Ortslage gazetteer.

Run after fetch_ortslage.py has produced bayern_ortslage_raw.json, and
after geocode.py has populated the main cache:

    cd etl/src
    <venv>/Scripts/python.exe geocode/crosscheck_ortslage.py

Two passes:

1. The doubtful categories flag_doubtful.py already reports - status
   "not_found" (Nominatim had nothing), or "ok" but outside Bavaria's
   bounding box (Nominatim matched a same-named place in another state).
   These are always corrected when AX_Ortslage has the name.

2. Every *other* "ok" entry, re-checked against AX_Ortslage even though
   it already looked fine - Bavaria has many villages that share a name
   with another village in a *different Bavarian* Landkreis (e.g.
   several "Kreuzberg"s), which the bbox/state check can't catch since
   both points are legitimately inside Bavaria. When the nearest
   AX_Ortslage match for the same name is implausibly far away (>50km -
   bigger than any single Landkreis), that is corrected the same way.
   Moderate gaps (5-50km, genuinely ambiguous - could be a large
   Landkreis, could be a wrong match) are left untouched but written to
   ortslage_distance_review.json for flag_doubtful.py to surface for
   manual review rather than silently guessing.

Multi-candidate names (AX_Ortslage records the same hamlet name more
than once across Bavaria) are disambiguated by picking whichever
candidate is closest to the average position of this place's Landkreis's
other already-geocoded organs - a cheap stand-in for a real spatial join
against Landkreis boundaries, good enough since we only need to pick the
right *one of a handful* of same-named villages, not a precise point.

Fixed entries get "quelle": "bayern_ortslage" so they stay distinguishable
from Nominatim-sourced ones; untouched entries keep their original shape.
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path

BBOX = {"lat_min": 47.2, "lat_max": 50.7, "lon_min": 8.9, "lon_max": 13.9}


def _norm(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


def _in_bavaria(lat: float, lon: float) -> bool:
    return BBOX["lat_min"] <= lat <= BBOX["lat_max"] and BBOX["lon_min"] <= lon <= BBOX["lon_max"]


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Equirectangular approximation - fine at Bavaria's scale (<400km, ~48-50 deg N)."""
    import math

    dlat = (a[0] - b[0]) * 111.0
    dlon = (a[1] - b[1]) * 111.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return (dlat**2 + dlon**2) ** 0.5


# Bigger than any single Bavarian Landkreis's extent - used both to pick among
# several same-named AX_Ortslage candidates (closest to the Landkreis anchor
# wins) and, just as importantly, as a plausibility gate: a name that matches
# only ONE candidate in the whole of Bavaria is not automatically trustworthy
# for a *specific* place just because it's the only option - e.g. Bavaria's
# AX_Ortslage has exactly one settlement actually named "Kreuzberg" (most
# "Kreuzberg"s are unregistered wayside-chapel hilltops, not villages), and
# applying it to every organ record that happens to say "Kreuzberg" would
# relocate several of them hundreds of km from where they actually are. If
# even the closest candidate is further than this from the place's own
# Landkreis, there is no trustworthy AX_Ortslage match - full stop.
PLAUSIBILITY_KM = 50
# Beyond this, treating the AX_Ortslage match as correct and Nominatim's as
# wrong is a safe call, not a guess.
HARD_MISMATCH_KM = 50
# Below this, worth a human glance but too easily a legitimately large
# Landkreis or an Ortsteil-vs-Gemeinde-seat offset to auto-correct.
SOFT_MISMATCH_KM = 5


def _pick_candidate(
    candidates: list[tuple[float, float]], anchor: tuple[float, float] | None
) -> tuple[float, float] | None:
    if anchor is None:
        return candidates[0] if len(candidates) == 1 else None  # can't disambiguate or sanity-check
    best = min(candidates, key=lambda c: _km(c, anchor))
    return best if _km(best, anchor) <= PLAUSIBILITY_KM else None


def run(site_data_dir: Path, cache_dir: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from geocode.geocode import collect_places  # noqa: E402

    places = collect_places(site_data_dir / "organs")
    cache = json.loads((cache_dir / "geocode_cache.json").read_text(encoding="utf-8"))
    ortslage_raw = json.loads((cache_dir / "bayern_ortslage_raw.json").read_text(encoding="utf-8"))

    name_index: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for name, lat, lon in ortslage_raw:
        name_index[_norm(name)].append((lat, lon))

    # Two anchor levels: Gemeinde (specific) and Landkreis (broader fallback).
    # Needed because Bydaten's LKR field uses the same literal placeholder
    # "krfr. Stadt" for every kreisfreie Stadt (Fuerth, Nuernberg, Muenchen,
    # Augsburg, ... - 4,922 organs) instead of naming each one, which makes
    # a Landkreis-only anchor average together a dozen unrelated cities
    # scattered across Bavaria - not just imprecise but actively wrong.
    # Gemeinde does hold the real city name even for those, so it is tried
    # first; Landkreis (reliable for everywhere else) is the fallback.
    gemeinde_points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    landkreis_points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for key, geo in cache.items():
        if geo.get("status") != "ok" or not _in_bavaria(geo["lat"], geo["lon"]):
            continue
        place = places.get(key, {})
        if place.get("gemeinde"):
            gemeinde_points[place["gemeinde"]].append((geo["lat"], geo["lon"]))
        if place.get("landkreis"):
            landkreis_points[place["landkreis"]].append((geo["lat"], geo["lon"]))

    def _centroid(points: dict[str, list[tuple[float, float]]]) -> dict[str, tuple[float, float]]:
        return {k: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) for k, pts in points.items()}

    gemeinde_centroid = _centroid(gemeinde_points)
    landkreis_centroid = _centroid(landkreis_points)

    def _best_candidate_for(key: str, place: dict) -> tuple[float, float] | None:
        candidates = name_index.get(_norm(place["ort"]))
        if not candidates:
            return None
        anchor = gemeinde_centroid.get(place.get("gemeinde")) or landkreis_centroid.get(place.get("landkreis"))
        return _pick_candidate(candidates, anchor)

    def _apply(key: str, place: dict, lat: float, lon: float) -> None:
        cache[key] = {
            "status": "ok",
            "lat": lat,
            "lon": lon,
            "display_name": f"{place['ort']} (Bayerische Vermessungsverwaltung, ATKIS Basis-DLM Ortslage)",
            "quelle": "bayern_ortslage",
            "fetched_at": time.strftime("%Y-%m-%d"),
        }

    fixed_not_found = 0
    fixed_wrong_state = 0
    unresolved = 0

    # Pass 1: the categories flag_doubtful.py already reports as doubtful.
    for key, geo in list(cache.items()):
        needs_fix = geo.get("status") == "not_found" or (
            geo.get("status") == "ok" and not _in_bavaria(geo["lat"], geo["lon"])
        )
        if not needs_fix:
            continue
        place = places.get(key)
        if not place or not place.get("ort"):
            continue
        best = _best_candidate_for(key, place)
        if best is None:
            unresolved += 1
            continue
        was_not_found = geo.get("status") == "not_found"
        _apply(key, place, *best)
        if was_not_found:
            fixed_not_found += 1
        else:
            fixed_wrong_state += 1

    # Pass 2: every remaining Nominatim "ok" entry, re-checked even though it
    # already looked fine - catches same-name mix-ups *within* Bavaria that
    # the bbox/state check structurally cannot see.
    fixed_same_state_mismatch = 0
    review: dict[str, dict] = {}
    for key, geo in cache.items():
        if geo.get("status") != "ok" or geo.get("quelle") == "bayern_ortslage":
            continue
        place = places.get(key)
        if not place or not place.get("ort"):
            continue
        best = _best_candidate_for(key, place)
        if best is None:
            continue
        distance = _km((geo["lat"], geo["lon"]), best)
        if distance > HARD_MISMATCH_KM:
            _apply(key, place, *best)
            fixed_same_state_mismatch += 1
        elif distance > SOFT_MISMATCH_KM:
            review[key] = {"distanz_km": round(distance, 1), "ortslage_lat": best[0], "ortslage_lon": best[1]}

    (cache_dir / "geocode_cache.json").write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (cache_dir / "ortslage_distance_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Vorher nicht gefunden, jetzt geloest: {fixed_not_found}")
    print(f"Vorher falscher Bundesland-Treffer, jetzt korrigiert: {fixed_wrong_state}")
    print(f"Bisher 'sicher', aber >{HARD_MISMATCH_KM}km von AX_Ortslage entfernt (korrigiert): {fixed_same_state_mismatch}")
    print(f"Moderate Abweichung ({SOFT_MISMATCH_KM}-{HARD_MISMATCH_KM}km), zur Pruefung vermerkt: {len(review)}")
    print(f"Weiterhin ungeloest (auch nicht in AX_Ortslage vorhanden): {unresolved}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    run(repo_root / "site" / "src" / "data", repo_root / "etl" / "cache")
