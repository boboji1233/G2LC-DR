"""Observation semantics for selected annotation operators."""

from __future__ import annotations

from typing import TypeAlias

from g2lc.operators.lattice import derivation_closure
from g2lc.operators.models import AnnotationOperator, DerivationGraph
from g2lc.types import EvidenceState, JsonScalar, scalar_equal, scalar_key

ObservationSignature: TypeAlias = tuple[tuple[str, str, JsonScalar], ...]


def operator_applicable(operator: AnnotationOperator, state: EvidenceState) -> bool:
    """Return whether every declared evidence condition holds in this state."""

    for requirement in operator.required_evidence_conditions:
        value = state.value(requirement.predicate_id)
        if value is None or not any(
            scalar_equal(value, allowed) for allowed in requirement.allowed_values
        ):
            return False
    return True


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
    return derivation_closure(exact, graph)


def derived_observation_values(
    operators: list[AnnotationOperator],
    graph: DerivationGraph,
    state: EvidenceState,
) -> dict[str, JsonScalar]:
    """Compute deterministic derived values from directly exact observations."""

    values: dict[str, JsonScalar] = {}
    for operator in operators:
        if not operator_applicable(operator, state):
            continue
        for predicate_id in operator.output_predicates:
            if predicate_id not in operator.value_mappings:
                values[predicate_id] = state.value(predicate_id)
    changed = True
    while changed:
        changed = False
        for rule in sorted(graph.rules, key=lambda item: item.id):
            source = rule.input_predicates[0]
            target = rule.output_predicates[0]
            if source not in values or target in values:
                continue
            source_value = values[source]
            if source_value is None:
                continue
            values[target] = rule.value_mapping[scalar_key(source_value)]
            changed = True
    return values


def derivations_consistent(state: EvidenceState, graph: DerivationGraph) -> bool:
    """Check every declared deterministic derivation against a complete state."""

    for rule in graph.rules:
        source = state.value(rule.input_predicates[0])
        target = state.value(rule.output_predicates[0])
        if source is None or target is None:
            return False
        expected = rule.value_mapping[scalar_key(source)]
        if not scalar_equal(expected, target):
            return False
    return True


def observation_signature(
    operators: list[AnnotationOperator],
    graph: DerivationGraph,
    state: EvidenceState,
) -> ObservationSignature:
    """Return deterministic saved and derived observations for a complete/partial state."""

    observations: list[tuple[str, str, JsonScalar]] = []
    for operator in sorted(operators, key=lambda item: item.id):
        applicable = operator_applicable(operator, state)
        observations.append((operator.id, "$applicable", applicable))
        if not applicable:
            continue
        for predicate_id in sorted(operator.output_predicates):
            value = state.value(predicate_id)
            mapping = operator.value_mappings.get(predicate_id)
            observed = mapping.get(scalar_key(value)) if mapping is not None else value
            observations.append((operator.id, predicate_id, observed))
    direct_exact = {
        predicate_id
        for operator in operators
        if operator_applicable(operator, state)
        for predicate_id in operator.output_predicates
        if predicate_id not in operator.value_mappings
    }
    derived = derived_observation_values(operators, graph, state)
    for predicate_id in sorted(set(derived) - direct_exact):
        observations.append(("$derived", predicate_id, derived[predicate_id]))
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


def distinguishes_scheme(
    operators: list[AnnotationOperator],
    graph: DerivationGraph,
    left: EvidenceState,
    right: EvidenceState,
) -> bool:
    """Return whether a prerequisite-closed operator scheme separates two states."""

    return observation_signature(operators, graph, left) != observation_signature(
        operators, graph, right
    )
