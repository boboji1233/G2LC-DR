"""Reference Python semantics for the versioned finite feasibility language."""

from __future__ import annotations

import itertools
from collections.abc import Iterator

import z3

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
from g2lc.types import EvidenceState, JsonScalar, scalar_equal, scalar_key


def _contains(values: list[JsonScalar], candidate: JsonScalar) -> bool:
    return any(scalar_equal(candidate, item) for item in values)


def condition_value(condition: EvidenceCondition, state: EvidenceState) -> bool | None:
    """Evaluate an equality atom on a partial state."""

    value = state.value(condition.predicate)
    if value is None:
        return None
    return scalar_equal(value, condition.equals)


def is_feasible_state(
    state: EvidenceState,
    ontology: EvidenceOntology,
    *,
    complete: bool,
) -> bool:
    """Return whether a complete state satisfies, or a partial state can satisfy, the DSL."""

    for constraint in ontology.feasibility.constraints:
        if isinstance(constraint, ImplicationConstraint):
            left = condition_value(constraint.antecedent, state)
            right = condition_value(constraint.consequent, state)
            if left is True and right is False:
                return False
            if complete and left is True and right is None:
                return False
        elif isinstance(constraint, MutualExclusionConstraint):
            if sum(condition_value(item, state) is True for item in constraint.conditions) > 1:
                return False
        elif isinstance(constraint, ConditionalAllowedConstraint):
            active = condition_value(constraint.antecedent, state)
            value = state.value(constraint.predicate)
            if (
                active is True
                and value is not None
                and not _contains(constraint.allowed_values, value)
            ):
                return False
            if complete and active is True and value is None:
                return False
        elif isinstance(constraint, (ExactlyOneConstraint, AtMostOneConstraint)):
            values = [condition_value(item, state) for item in constraint.conditions]
            true_count = sum(item is True for item in values)
            if true_count > 1:
                return False
            if isinstance(constraint, ExactlyOneConstraint):
                if complete and true_count != 1:
                    return False
                if not complete and true_count == 0 and all(item is False for item in values):
                    return False
        elif isinstance(constraint, DerivedEqualityConstraint):
            source = state.value(constraint.source_predicate)
            target = state.value(constraint.target_predicate)
            if source is None or target is None:
                if complete:
                    return False
                continue
            expected = (
                constraint.value_mapping.get(scalar_key(source))
                if constraint.value_mapping
                else source
            )
            if expected is None or not scalar_equal(expected, target):
                return False
        elif isinstance(constraint, ParentChildConstraint):
            parent = state.value(constraint.parent_predicate)
            child = state.value(constraint.child_predicate)
            if parent is None or child is None:
                if complete:
                    return False
                continue
            if _contains(constraint.when_parent_values, parent) and not _contains(
                constraint.allowed_child_values, child
            ):
                return False
        else:  # pragma: no cover - discriminated union is exhaustive
            raise AssertionError(type(constraint).__name__)
    return True


def feasible_completions(
    state: EvidenceState,
    ontology: EvidenceOntology,
) -> Iterator[EvidenceState]:
    """Yield every feasible complete ontology state extending a validated partial state."""

    predicates = sorted(ontology.predicates, key=lambda item: item.id)
    missing = [item for item in predicates if not state.known(item.id)]
    domains = [item.allowed_values for item in missing]
    for values in itertools.product(*domains):
        completion = EvidenceState(
            values={
                **state.values,
                **{item.id: value for item, value in zip(missing, values, strict=True)},
            }
        )
        if is_feasible_state(completion, ontology, complete=True):
            yield completion


def feasibility_predicates(ontology: EvidenceOntology) -> set[str]:
    """Return every predicate referenced transitively by the feasibility program."""

    result: set[str] = set()
    for constraint in ontology.feasibility.constraints:
        if isinstance(constraint, ImplicationConstraint):
            result.update([constraint.antecedent.predicate, constraint.consequent.predicate])
        elif isinstance(
            constraint, (MutualExclusionConstraint, ExactlyOneConstraint, AtMostOneConstraint)
        ):
            result.update(item.predicate for item in constraint.conditions)
        elif isinstance(constraint, ConditionalAllowedConstraint):
            result.update([constraint.antecedent.predicate, constraint.predicate])
        elif isinstance(constraint, DerivedEqualityConstraint):
            result.update([constraint.source_predicate, constraint.target_predicate])
        elif isinstance(constraint, ParentChildConstraint):
            result.update([constraint.parent_predicate, constraint.child_predicate])
    return result


def feasibility_constraints_z3(
    ontology: EvidenceOntology,
    variables: dict[str, z3.ArithRef],
    indices: dict[str, dict[str, int]],
) -> list[z3.BoolRef]:
    """Translate the feasibility program to the exact complete-state SMT contract."""

    def condition(item: EvidenceCondition) -> z3.BoolRef:
        return variables[item.predicate] == indices[item.predicate][scalar_key(item.equals)]

    result: list[z3.BoolRef] = []
    for constraint in ontology.feasibility.constraints:
        if isinstance(constraint, ImplicationConstraint):
            result.append(
                z3.Implies(condition(constraint.antecedent), condition(constraint.consequent))
            )
        elif isinstance(constraint, MutualExclusionConstraint):
            result.append(z3.AtMost(*[condition(item) for item in constraint.conditions], 1))
        elif isinstance(constraint, ConditionalAllowedConstraint):
            allowed = z3.Or(
                *[
                    variables[constraint.predicate]
                    == indices[constraint.predicate][scalar_key(value)]
                    for value in constraint.allowed_values
                ]
            )
            result.append(z3.Implies(condition(constraint.antecedent), allowed))
        elif isinstance(constraint, ExactlyOneConstraint):
            result.append(z3.PbEq([(condition(item), 1) for item in constraint.conditions], 1))
        elif isinstance(constraint, AtMostOneConstraint):
            result.append(z3.AtMost(*[condition(item) for item in constraint.conditions], 1))
        elif isinstance(constraint, DerivedEqualityConstraint):
            source_domain = ontology.predicate(constraint.source_predicate).allowed_values
            result.append(
                z3.Or(
                    *[
                        z3.And(
                            variables[constraint.source_predicate] == source_index,
                            variables[constraint.target_predicate]
                            == indices[constraint.target_predicate][
                                scalar_key(
                                    constraint.value_mapping[scalar_key(source_value)]
                                    if constraint.value_mapping
                                    else source_value
                                )
                            ],
                        )
                        for source_index, source_value in enumerate(source_domain)
                    ]
                )
            )
        elif isinstance(constraint, ParentChildConstraint):
            parent_active = z3.Or(
                *[
                    variables[constraint.parent_predicate]
                    == indices[constraint.parent_predicate][scalar_key(value)]
                    for value in constraint.when_parent_values
                ]
            )
            child_allowed = z3.Or(
                *[
                    variables[constraint.child_predicate]
                    == indices[constraint.child_predicate][scalar_key(value)]
                    for value in constraint.allowed_child_values
                ]
            )
            result.append(z3.Implies(parent_active, child_allowed))
    return result
