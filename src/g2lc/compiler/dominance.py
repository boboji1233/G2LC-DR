"""Conservative operator-dominance analysis."""

from __future__ import annotations

from g2lc.compiler.problem import FiniteProblem
from g2lc.operators.lattice import operator_prerequisite_closure


def dominated_operators(finite: FiniteProblem) -> dict[str, str]:
    """Map safely dominated operators to a deterministic dominating operator.

    Stability is checked even when its current objective weight is zero, because a
    cheaper but less stable operator is not scientifically interchangeable.
    """

    required = set(finite.loaded.config.required_operators)
    result: dict[str, str] = {}
    operators = sorted(finite.operators, key=lambda item: item.id)
    operator_map = {item.id: item for item in operators}
    for candidate in operators:
        if candidate.id in required:
            continue
        candidate_closure = operator_prerequisite_closure([candidate.id], operator_map)
        candidate_cost = sum(operator_map[item].cost for item in candidate_closure)
        candidate_instability = sum(operator_map[item].instability for item in candidate_closure)
        dominators = []
        for other in operators:
            if other.id == candidate.id:
                continue
            other_closure = operator_prerequisite_closure([other.id], operator_map)
            other_cost = sum(operator_map[item].cost for item in other_closure)
            other_instability = sum(operator_map[item].instability for item in other_closure)
            if (
                finite.coverage[other.id].issuperset(finite.coverage[candidate.id])
                and other_cost <= candidate_cost
                and other_instability <= candidate_instability
                and (
                    other_cost < candidate_cost
                    or other_instability < candidate_instability
                    or other_closure < candidate_closure
                )
            ):
                dominators.append(other)
        if dominators:
            result[candidate.id] = min(dominators, key=lambda item: item.id).id
    return result
