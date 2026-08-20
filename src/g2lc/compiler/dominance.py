"""Conservative operator-dominance analysis."""

from __future__ import annotations

from g2lc.compiler.problem import FiniteProblem


def dominated_operators(finite: FiniteProblem) -> dict[str, str]:
    """Map safely dominated operators to a deterministic dominating operator.

    Stability is checked even when its current objective weight is zero, because a
    cheaper but less stable operator is not scientifically interchangeable.
    """

    required = set(finite.loaded.config.required_operators)
    result: dict[str, str] = {}
    operators = sorted(finite.operators, key=lambda item: item.id)
    for candidate in operators:
        if candidate.id in required:
            continue
        dominators = [
            other
            for other in operators
            if other.id != candidate.id
            and finite.coverage[other.id].issuperset(finite.coverage[candidate.id])
            and other.cost <= candidate.cost
            and other.instability <= candidate.instability
            and (
                other.cost < candidate.cost
                or other.instability < candidate.instability
                or other.id < candidate.id
            )
        ]
        if dominators:
            result[candidate.id] = min(dominators, key=lambda item: item.id).id
    return result
