"""Clean one Bydaten row into the organ record shape consumed by the site."""
from __future__ import annotations

from . import bauer_match
from .dispo_parser import parse_dispo
from .jahr import parse_jahr
from .postleitzahl import clean_plz

# Bavaria's 7 Regierungsbezirke. Checked against the real data: RBZ also
# contains a handful of case-typo variants ("Ufr", "Opf") that Access's
# case-insensitive GROUP BY silently merges but Python string equality
# does not - normalize here so site code never has to think about it.
_CANONICAL_RBZ = ("OB", "NB", "OPf", "OFr", "MFr", "UFr", "Schw")
_RBZ_LOOKUP = {code.lower(): code for code in _CANONICAL_RBZ}


def _normalize_rbz(raw: str | None) -> tuple[str | None, str | None]:
    """Returns (normalized_code_or_None, raw_value_if_unrecognized_or_None)."""
    if not raw:
        return None, None
    canonical = _RBZ_LOOKUP.get(raw.strip().lower())
    if canonical:
        return canonical, None
    return None, raw


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _place_key(ort: str | None, plz: str | None, gemeinde: str | None, landkreis: str | None) -> str | None:
    if ort and plz:
        return f"{ort.strip().lower()}|{plz}"
    if ort and (gemeinde or landkreis):
        return f"{ort.strip().lower()}|{(gemeinde or landkreis).strip().lower()}"
    return None


def clean_bydaten_row(row: dict, bauer_lookup: dict[str, int]) -> dict:
    plz = clean_plz(row.get("POST"))
    ort = _str_or_none(row.get("ORT"))
    gemeinde = _str_or_none(row.get("GDE"))
    landkreis = _str_or_none(row.get("LKR"))
    rbz, rbz_raw_unrecognized = _normalize_rbz(row.get("RBZ"))

    return {
        "id": row["ID"],
        "ort": ort,
        "gemeinde": gemeinde,
        "landkreis": landkreis,
        "regierungsbezirk": rbz,
        "kirche": _str_or_none(row.get("KIRCHE")),
        "adresse": {
            "zeile1": _str_or_none(row.get("ADRESSE1")),
            "zeile2": _str_or_none(row.get("ADRESSE2")),
            "plz": plz,
            "ort": _str_or_none(row.get("ADRESSE3")),
        },
        "erhalten": bool(row.get("ERHALTEN")),
        "denkmalorgel": bool(row.get("DO")),
        **bauer_match.match_bauer(row.get("BAUER"), bauer_lookup),
        "jahr": parse_jahr(row.get("JAHR")),
        "manuale": _int_or_none(row.get("M")),
        "register": _int_or_none(row.get("REG")),
        "dispo": parse_dispo(row.get("DISPO")),
        "bemerkung": _str_or_none(row.get("BEMERKUNG")),
        "memo": _str_or_none(row.get("MEMO")),
        "place_key": _place_key(ort, plz, gemeinde, landkreis),
        "_unclear": {
            "dp": bool(row.get("DP")),
            "kl": _str_or_none(row.get("KL")),
            "t": _str_or_none(row.get("T")),
            "satz": row.get("SATZ"),
            "rbz_raw_unrecognized": rbz_raw_unrecognized,
        },
    }
