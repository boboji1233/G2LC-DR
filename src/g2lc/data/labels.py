"""Three-state dataset label semantics."""

from __future__ import annotations

from g2lc.types import EvidenceLabel


def normalize_label(value: str | None) -> EvidenceLabel:
    """Normalize an explicit label token; absence is always UNKNOWN."""

    if value is None or not value.strip():
        return EvidenceLabel.UNKNOWN
    try:
        return EvidenceLabel(value.strip().upper())
    except ValueError as exc:
        raise ValueError(
            f"invalid label state {value!r}; expected POSITIVE, NEGATIVE, or UNKNOWN"
        ) from exc
