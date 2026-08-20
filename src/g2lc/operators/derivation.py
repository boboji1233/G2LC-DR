"""Observation semantics for selected annotation operators."""

from __future__ import annotations

from typing import TypeAlias

from g2lc.operators.lattice import derivation_closure
from g2lc.operators.models import AnnotationOperator, DerivationGraph
from g2lc.types import EvidenceState, JsonScalar, scalar_key

ObservationSignature: TypeAlias = tuple[tuple[str, str, JsonScalar], ...]


def exact_observed_predicates(
    operators: list[AnnotationOperator], graph: DerivationGraph
) -> set[str]:
    """Return exact predicates; coarsened direct mappings do not seed derivations."""

    exact: set[str] = set()
    for operator in operators:
        exact.update(
            predicate
            for predicate in operator.output_predicates
            if predicate not in operator.value_mappings
        )
        exact.update(operator.derivable_outputs)
    return derivation_closure(exact, graph)


def observation_signature(
    operators: list[AnnotationOperator],
    graph: DerivationGraph,
    state: EvidenceState,
) -> ObservationSignature:
    """Return deterministic saved and derived observations for a complete/partial state."""

    observations: list[tuple[str, str, JsonScalar]] = []
    for operator in sorted(operators, key=lambda item: item.id):
        for predicate_id in sorted(operator.output_predicates):
            value = state.value(predicate_id)
            mapping = operator.value_mappings.get(predicate_id)
            observed = mapping.get(scalar_key(value)) if mapping is not None else value
            observations.append((operator.id, predicate_id, observed))
    for predicate_id in sorted(exact_observed_predicates(operators, graph)):
        observations.append(("$derived", predicate_id, state.value(predicate_id)))
    return tuple(observations)


def distinguishes(
    operator: AnnotationOperator,
    graph: DerivationGraph,
    left: EvidenceState,
    right: EvidenceState,
) -> bool:
    """Return whether one operator separates two evidence states."""

    return observation_signature([operator], graph, left) != observation_signature(
        [operator], graph, right
    )
