"""Operator/derivation validation and exact-observation closure."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from g2lc.errors import OperatorValidationError
from g2lc.ontology.models import EvidenceOntology
from g2lc.operators.models import DerivationGraph, OperatorCatalogue
from g2lc.types import scalar_equal, scalar_key
from g2lc.utils.io import load_yaml, validation_error


def load_operator_catalogue(path: str | Path) -> OperatorCatalogue:
    """Load an operator catalogue with structural validation."""

    try:
        return OperatorCatalogue.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise validation_error(path, exc) from exc


def load_derivation_graph(path: str | Path) -> DerivationGraph:
    """Load a derivation graph with structural validation."""

    try:
        return DerivationGraph.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise validation_error(path, exc) from exc


def validate_operators(
    catalogue: OperatorCatalogue,
    graph: DerivationGraph,
    ontology: EvidenceOntology,
) -> None:
    """Check predicate references, mappings, modalities and DAG acyclicity."""

    predicates = ontology.predicate_map()
    operator_map = catalogue.operator_map()
    dependency_edges: dict[str, set[str]] = {item: set() for item in operator_map}
    for operator in catalogue.operators:
        references = set(operator.output_predicates) | {
            item.predicate_id for item in operator.required_evidence_conditions
        }
        unknown = sorted(references - predicates.keys())
        if unknown:
            raise OperatorValidationError(
                f"operator {operator.id!r} references unknown predicates {unknown}"
            )
        for predicate_id, mapping in operator.value_mappings.items():
            expected = {scalar_key(value) for value in predicates[predicate_id].allowed_values}
            actual = set(mapping)
            if actual != expected:
                missing = sorted(expected - actual)
                extra = sorted(actual - expected)
                raise OperatorValidationError(
                    f"operator {operator.id!r} mapping for {predicate_id!r} must cover its "
                    f"entire domain; missing={missing}, extra={extra}"
                )
        unknown_operators = sorted(set(operator.required_operator_ids) - operator_map.keys())
        if unknown_operators:
            raise OperatorValidationError(
                f"operator {operator.id!r} requires unknown operators {unknown_operators}"
            )
        dependency_edges[operator.id].update(operator.required_operator_ids)
        for requirement in operator.required_evidence_conditions:
            domain = predicates[requirement.predicate_id].allowed_values
            invalid = [
                item
                for item in requirement.allowed_values
                if not any(scalar_equal(item, allowed) for allowed in domain)
            ]
            if invalid:
                raise OperatorValidationError(
                    f"operator {operator.id!r} evidence requirement has out-of-domain "
                    f"values {invalid!r}"
                )
            prerequisite_outputs = {
                predicate_id
                for operator_id in operator.required_operator_ids
                for predicate_id in operator_map[operator_id].output_predicates
            }
            if requirement.predicate_id not in prerequisite_outputs:
                raise OperatorValidationError(
                    f"operator {operator.id!r} evidence prerequisite "
                    f"{requirement.predicate_id!r} is not observed by a required operator"
                )
        if not set(operator.required_modalities).issubset(operator.modalities):
            raise OperatorValidationError(
                f"operator {operator.id!r} required_modalities must be a subset of modalities"
            )
    _reject_named_cycles(dependency_edges, "operator prerequisite")
    edges: dict[str, set[str]] = {predicate_id: set() for predicate_id in predicates}
    for rule in graph.rules:
        if len(rule.input_predicates) != 1 or len(rule.output_predicates) != 1:
            raise OperatorValidationError(f"derivation rule {rule.id!r} must be unary in Stage 1.5")
        references = set(rule.input_predicates) | set(rule.output_predicates)
        unknown = sorted(references - predicates.keys())
        if unknown:
            raise OperatorValidationError(
                f"derivation rule {rule.id!r} references unknown predicates {unknown}"
            )
        overlap = sorted(set(rule.input_predicates) & set(rule.output_predicates))
        if overlap:
            raise OperatorValidationError(
                f"derivation rule {rule.id!r} has inputs also declared as outputs: {overlap}"
            )
        for source in rule.input_predicates:
            edges[source].update(rule.output_predicates)
    _reject_cycles(edges)
    for rule in graph.rules:
        source_predicate = predicates[rule.input_predicates[0]]
        target_predicate = predicates[rule.output_predicates[0]]
        expected = {scalar_key(value) for value in source_predicate.allowed_values}
        if set(rule.value_mapping) != expected:
            raise OperatorValidationError(
                f"derivation rule {rule.id!r} value_mapping must be total over its source "
                f"domain; expected={sorted(expected)}"
            )
        invalid = [
            value
            for value in rule.value_mapping.values()
            if not any(scalar_equal(value, allowed) for allowed in target_predicate.allowed_values)
        ]
        if invalid:
            raise OperatorValidationError(
                f"derivation rule {rule.id!r} maps to out-of-domain values {invalid!r}"
            )


def _reject_named_cycles(edges: dict[str, set[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            start = trail.index(node)
            cycle = [*trail[start:], node]
            raise OperatorValidationError(f"cyclic {label} graph: {' -> '.join(cycle)}")
        if node in visited:
            return
        visiting.add(node)
        for target in sorted(edges[node]):
            visit(target, [*trail, target])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        visit(node, [node])


def _reject_cycles(edges: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            start = trail.index(node)
            cycle = [*trail[start:], node]
            raise OperatorValidationError(f"cyclic derivation graph: {' -> '.join(cycle)}")
        if node in visited:
            return
        visiting.add(node)
        for target in sorted(edges[node]):
            visit(target, [*trail, target])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        visit(node, [node])


def derivation_closure(initial: set[str], graph: DerivationGraph) -> set[str]:
    """Compute the least fixed point of exact predicate derivations."""

    closure = set(initial)
    changed = True
    while changed:
        changed = False
        for rule in sorted(graph.rules, key=lambda item: item.id):
            if set(rule.input_predicates).issubset(closure):
                before = len(closure)
                closure.update(rule.output_predicates)
                changed = changed or len(closure) != before
    return closure
