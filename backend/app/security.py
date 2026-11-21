"""Strip credentials from messages before they are logged or stored."""

from __future__ import annotations

import re

_SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*(?:bearer\s+|apikey\s+)?\S+"),
    re.compile(r"(?i)\b(?:apikey|bearer)\s+\S+"),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
)


def redact_secrets(text: str, limit: int = 500) -> str:
    cleaned = text
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned
