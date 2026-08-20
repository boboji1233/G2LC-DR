"""Strong Kleene three-valued logic."""

from __future__ import annotations

from enum import StrEnum


class TriValue(StrEnum):
    """Truth value where UNKNOWN is information absence, not falsehood."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"

    def __invert__(self) -> TriValue:
        if self is TriValue.TRUE:
            return TriValue.FALSE
        if self is TriValue.FALSE:
            return TriValue.TRUE
        return TriValue.UNKNOWN


def tri_and(values: list[TriValue]) -> TriValue:
    """Evaluate strong Kleene conjunction."""

    if not values:
        return TriValue.TRUE
    if TriValue.FALSE in values:
        return TriValue.FALSE
    if TriValue.UNKNOWN in values:
        return TriValue.UNKNOWN
    return TriValue.TRUE


def tri_or(values: list[TriValue]) -> TriValue:
    """Evaluate strong Kleene disjunction."""

    if not values:
        return TriValue.FALSE
    if TriValue.TRUE in values:
        return TriValue.TRUE
    if TriValue.UNKNOWN in values:
        return TriValue.UNKNOWN
    return TriValue.FALSE
