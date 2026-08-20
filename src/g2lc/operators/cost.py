"""Explicit development cost functions."""

from __future__ import annotations

from g2lc.operators.models import AnnotationOperator


def weighted_cost(operator: AnnotationOperator, instability_weight: float) -> float:
    """Combine declared cost and instability without introducing empirical values."""

    if instability_weight < 0:
        raise ValueError("instability_weight must be nonnegative")
    return operator.cost + instability_weight * operator.instability


def scheme_cost(operators: list[AnnotationOperator], instability_weight: float) -> float:
    """Return a stable rounded total for a selected scheme."""

    return round(sum(weighted_cost(item, instability_weight) for item in operators), 9)
