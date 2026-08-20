"""Semantic ontology validation beyond field-level schema checks."""

from __future__ import annotations

from g2lc.errors import OntologyValidationError
from g2lc.ontology.models import (
    AtMostOneConstraint,
    ConditionalAllowedConstraint,
    DerivedEqualityConstraint,
    EvidenceCondition,
    EvidenceOntology,
    ExactlyOneConstraint,
    ImplicationConstraint,
    MutualExclusionConstraint,
    ParentChildConstraint,
)
from g2lc.types import JsonScalar, scalar_equal, scalar_key


def validate_ontology(ontology: EvidenceOntology) -> None:
    """Check references and reject parent/requirement cycles."""

    predicates = ontology.predicate_map()
    for predicate in ontology.predicates:
        references = list(predicate.requires)
        if predicate.parent_predicate is not None:
            references.append(predicate.parent_predicate)
        unknown = sorted(set(references) - predicates.keys())
        if unknown:
            raise OntologyValidationError(
                f"predicate {predicate.id!r} references unknown predicates {unknown}"
            )
        if predicate.id in references:
            raise OntologyValidationError(f"predicate {predicate.id!r} references itself")

    edges: dict[str, list[str]] = {
        item.id: sorted(
            set(item.requires)
            | ({item.parent_predicate} if item.parent_predicate is not None else set())
        )
        for item in ontology.predicates
    }
    _reject_cycles(edges, "ontology dependency")
    _validate_feasibility(ontology)


def _in_domain(value: JsonScalar, values: list[JsonScalar]) -> bool:
    return any(scalar_equal(value, item) for item in values)


def _validate_condition(condition: EvidenceCondition, ontology: EvidenceOntology) -> None:
    predicates = ontology.predicate_map()
    if condition.predicate not in predicates:
        raise OntologyValidationError(
            f"feasibility condition references unknown predicate {condition.predicate!r}"
        )
    if not _in_domain(condition.equals, predicates[condition.predicate].allowed_values):
        raise OntologyValidationError(
            f"feasibility condition for {condition.predicate!r} has out-of-domain value "
            f"{condition.equals!r}"
        )


def _validate_feasibility(ontology: EvidenceOntology) -> None:
    predicates = ontology.predicate_map()
    for constraint in ontology.feasibility.constraints:
        if isinstance(constraint, ImplicationConstraint):
            _validate_condition(constraint.antecedent, ontology)
            _validate_condition(constraint.consequent, ontology)
        elif isinstance(
            constraint, (MutualExclusionConstraint, ExactlyOneConstraint, AtMostOneConstraint)
        ):
            for condition in constraint.conditions:
                _validate_condition(condition, ontology)
        elif isinstance(constraint, ConditionalAllowedConstraint):
            _validate_condition(constraint.antecedent, ontology)
            if constraint.predicate not in predicates:
                raise OntologyValidationError(
                    f"conditional_allowed references unknown predicate {constraint.predicate!r}"
                )
            invalid = [
                item
                for item in constraint.allowed_values
                if not _in_domain(item, predicates[constraint.predicate].allowed_values)
            ]
            if invalid:
                raise OntologyValidationError(
                    f"conditional_allowed has out-of-domain values {invalid!r}"
                )
        elif isinstance(constraint, DerivedEqualityConstraint):
            unknown = sorted(
                {constraint.source_predicate, constraint.target_predicate} - predicates.keys()
            )
            if unknown:
                raise OntologyValidationError(
                    f"derived_equality references unknown predicates {unknown}"
                )
            source_domain = predicates[constraint.source_predicate].allowed_values
            target_domain = predicates[constraint.target_predicate].allowed_values
            if constraint.value_mapping:
                expected = {scalar_key(item) for item in source_domain}
                if set(constraint.value_mapping) != expected:
                    raise OntologyValidationError(
                        "derived_equality value_mapping must be total over its source domain"
                    )
                if any(
                    not _in_domain(item, target_domain)
                    for item in constraint.value_mapping.values()
                ):
                    raise OntologyValidationError(
                        "derived_equality maps to an out-of-domain target value"
                    )
        elif isinstance(constraint, ParentChildConstraint):
            unknown = sorted(
                {constraint.parent_predicate, constraint.child_predicate} - predicates.keys()
            )
            if unknown:
                raise OntologyValidationError(
                    f"parent_child references unknown predicates {unknown}"
                )
            if any(
                not _in_domain(item, predicates[constraint.parent_predicate].allowed_values)
                for item in constraint.when_parent_values
            ) or any(
                not _in_domain(item, predicates[constraint.child_predicate].allowed_values)
                for item in constraint.allowed_child_values
            ):
                raise OntologyValidationError("parent_child contains out-of-domain values")


def _reject_cycles(edges: dict[str, list[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            start = trail.index(node)
            cycle = [*trail[start:], node]
            raise OntologyValidationError(f"{label} cycle: {' -> '.join(cycle)}")
        if node in visited:
            return
        visiting.add(node)
        for target in edges[node]:
            visit(target, [*trail, target])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        visit(node, [node])
