"""Clean Bydaten.POST, stored as a Double in Access (e.g. 80331.0, 0.0, NaN)."""
from __future__ import annotations

import math


def clean_plz(raw: float | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, float) and math.isnan(raw):
        return None
    value = int(round(raw))
    if value <= 0:
        return None
    return f"{value:05d}"
