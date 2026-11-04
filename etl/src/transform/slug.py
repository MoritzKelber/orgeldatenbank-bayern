"""Turn an arbitrary title string into a URL-safe slug."""
from __future__ import annotations

import re

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    text = text.translate(_UMLAUT_MAP).lower()
    text = _NON_SLUG_RE.sub("-", text).strip("-")
    return text or "x"
