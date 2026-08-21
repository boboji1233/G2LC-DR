"""Guideline semantic validation against an evidence ontology."""

from __future__ import annotations

import itertools
import math
from datetime import date

import z3

from g2lc.errors import GuidelineValidationError
from g2lc.guidelines.ast import (
    And,
    Equals,
    Expression,
    GreaterEqual,
    Guideline,
    GuidelineBundle,
    InSet,
    Known,
    LessEqual,
    Not,
    Or,
)
from g2lc.guidelines.evaluator import evaluate_expression
from g2lc.guidelines.trivalued import TriValue
from g2lc.ontology.feasibility import feasibility_constraints_z3
from g2lc.ontology.models import EvidenceOntology
from g2lc.operators.derivation import derivations_consistent
from g2lc.operators.models import DerivationGraph
from g2lc.types import EvidenceState, ReviewStatus, ValueType, scalar_equal, scalar_key
from g2lc.utils.io import canonical_json


def validate_guidelines(
    bundle: GuidelineBundle,
    ontology: EvidenceOntology | None = None,
    derivations: DerivationGraph | None = None,
    *,
    conflict_state_limit: int = 10_000,
) -> None:
    """Validate provenance, action shape, predicate types and finite conflicts."""

    for guideline in bundle.guidelines:
        _validate_guideline(
            guideline,
            bundle.synthetic,
            ontology,
            derivations,
            conflict_state_limit,
        )


def _validate_guideline(
    guideline: Guideline,
    bundle_synthetic: bool,
    ontology: EvidenceOntology | None,
    derivations: DerivationGraph | None,
    conflict_state_limit: int,
) -> None:
    schema = set(guideline.action_schema)
    if guideline.provenance.version != guideline.version:
        raise GuidelineValidationError(
            f"guideline {guideline.id!r} provenance version must equal guideline version"
        )
    if bundle_synthetic and guideline.provenance.review_status is not ReviewStatus.SYNTHETIC:
        raise GuidelineValidationError(
            f"synthetic guideline {guideline.id!r} must use SYNTHETIC review_status"
        )
    if not bundle_synthetic:
        try:
            date.fromisoformat(guideline.effective_date)
        except ValueError as exc:
            raise GuidelineValidationError(
                f"guideline {guideline.id!r} effective_date must be an ISO YYYY-MM-DD date"
            ) from exc
    for rule in guideline.rules:
        if rule.provenance.version != guideline.version:
            raise GuidelineValidationError(
                f"clause {guideline.id}.{rule.id} provenance version does not match guideline"
            )
        if bundle_synthetic and rule.provenance.review_status is not ReviewStatus.SYNTHETIC:
            raise GuidelineValidationError(
                f"synthetic clause {guideline.id}.{rule.id} must use SYNTHETIC review_status"
            )
        action_keys = set(rule.action.values)
        if action_keys != schema:
            raise GuidelineValidationError(
                f"clause {guideline.id}.{rule.id} action keys must exactly match schema; "
                f"missing={sorted(schema - action_keys)}, extra={sorted(action_keys - schema)}"
            )
    if guideline.default_action is not None:
        action_keys = set(guideline.default_action.values)
        if action_keys != schema:
            raise GuidelineValidationError(
                f"guideline {guideline.id!r} default action keys must exactly match schema; "
                f"missing={sorted(schema - action_keys)}, extra={sorted(action_keys - schema)}"
            )
    if ontology is None:
        return
    for rule in guideline.rules:
        _validate_expression(rule.when, ontology, f"{guideline.id}.{rule.id}")
    state_count = math.prod(len(item.allowed_values) for item in ontology.predicates)
    if state_count <= conflict_state_limit:
        _reject_same_priority_conflicts(guideline, ontology, derivations)
    else:
        _reject_same_priority_conflicts_smt(guideline, ontology, derivations)


def _validate_expression(
    expression: Expression,
    ontology: EvidenceOntology,
    context: str,
) -> None:
    if isinstance(expression, (And, Or)):
        for term in expression.terms:
            _validate_expression(term, ontology, context)
        return
    if isinstance(expression, Not):
        _validate_expression(expression.term, ontology, context)
        return
    predicates = ontology.predicate_map()
    if expression.predicate not in predicates:
        raise GuidelineValidationError(
            f"clause {context} references unknown predicate {expression.predicate!r}"
        )
    predicate = predicates[expression.predicate]
    if isinstance(expression, (GreaterEqual, LessEqual)):
        if predicate.value_type not in {ValueType.INTEGER, ValueType.NUMBER}:
            raise GuidelineValidationError(
                f"clause {context} uses numeric comparison on non-numeric predicate "
                f"{predicate.id!r}"
            )
    elif isinstance(expression, Equals):
        if not any(scalar_equal(expression.value, item) for item in predicate.allowed_values):
            raise GuidelineValidationError(
                f"clause {context} compares {predicate.id!r} to out-of-domain value "
                f"{expression.value!r}"
            )
    elif isinstance(expression, InSet):
        invalid = [
            value
            for value in expression.values
            if not any(scalar_equal(value, item) for item in predicate.allowed_values)
        ]
        if invalid:
            raise GuidelineValidationError(
                f"clause {context} uses out-of-domain values {invalid} for {predicate.id!r}"
            )


def _reject_same_priority_conflicts(
    guideline: Guideline,
    ontology: EvidenceOntology,
    derivations: DerivationGraph | None,
) -> None:
    predicates = sorted(ontology.predicates, key=lambda item: item.id)
    domains = [item.allowed_values for item in predicates]
    for values in itertools.product(*domains):
        state = EvidenceState(
            values={item.id: value for item, value in zip(predicates, values, strict=True)}
        )
        from g2lc.ontology.feasibility import is_feasible_state

        if not is_feasible_state(state, ontology, complete=True):
            continue
        if derivations is not None and not derivations_consistent(state, derivations):
            continue
        triggered = [
            rule
            for rule in guideline.rules
            if evaluate_expression(rule.when, state, ontology) is TriValue.TRUE
        ]
        by_priority: dict[int, list[tuple[str, str]]] = {}
        for rule in triggered:
            by_priority.setdefault(rule.priority, []).append(
                (rule.id, canonical_json(rule.action.model_dump(mode="json")))
            )
        for priority, actions in by_priority.items():
            if len({action for _, action in actions}) > 1:
                rule_ids = sorted(rule_id for rule_id, _ in actions)
                raise GuidelineValidationError(
                    f"guideline {guideline.id!r} has conflicting clauses {rule_ids} at "
                    f"priority {priority}; witness state={state.values}"
                )


def _expression_to_z3(
    expression: Expression,
    variables: dict[str, z3.ArithRef],
    ontology: EvidenceOntology,
    indices: dict[str, dict[str, int]],
) -> z3.BoolRef:
    if isinstance(expression, And):
        return z3.And(
            *[_expression_to_z3(item, variables, ontology, indices) for item in expression.terms]
        )
    if isinstance(expression, Or):
        return z3.Or(
            *[_expression_to_z3(item, variables, ontology, indices) for item in expression.terms]
        )
    if isinstance(expression, Not):
        return z3.Not(_expression_to_z3(expression.term, variables, ontology, indices))
    if isinstance(expression, Known):
        return z3.BoolVal(True)
    variable = variables[expression.predicate]
    if isinstance(expression, Equals):
        return variable == indices[expression.predicate][scalar_key(expression.value)]
    if isinstance(expression, InSet):
        return z3.Or(
            *[
                variable == indices[expression.predicate][scalar_key(item)]
                for item in expression.values
            ]
        )
    predicate = ontology.predicate(expression.predicate)
    allowed = []
    for index, value in enumerate(predicate.allowed_values):
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        greater_match = isinstance(expression, GreaterEqual) and value >= expression.value
        lesser_match = isinstance(expression, LessEqual) and value <= expression.value
        if greater_match or lesser_match:
            allowed.append(index)
    return z3.Or(*[variable == item for item in allowed])


def _reject_same_priority_conflicts_smt(
    guideline: Guideline,
    ontology: EvidenceOntology,
    derivations: DerivationGraph | None,
) -> None:
    variables = {item.id: z3.Int(f"validation__{item.id}") for item in ontology.predicates}
    indices = {
        item.id: {scalar_key(value): index for index, value in enumerate(item.allowed_values)}
        for item in ontology.predicates
    }
    base = z3.Solver()
    base.set(timeout=10_000)
    for predicate in ontology.predicates:
        base.add(variables[predicate.id] >= 0)
        base.add(variables[predicate.id] < len(predicate.allowed_values))
    base.add(*feasibility_constraints_z3(ontology, variables, indices))
    if derivations is not None:
        for rule in derivations.rules:
            source_id = rule.input_predicates[0]
            target_id = rule.output_predicates[0]
            for source_index, source_value in enumerate(
                ontology.predicate(source_id).allowed_values
            ):
                base.add(
                    z3.Implies(
                        variables[source_id] == source_index,
                        variables[target_id]
                        == indices[target_id][
                            scalar_key(rule.value_mapping[scalar_key(source_value)])
                        ],
                    )
                )
    for left_index, left in enumerate(guideline.rules):
        for right in guideline.rules[left_index + 1 :]:
            if left.priority != right.priority or left.action == right.action:
                continue
            base.push()
            base.add(_expression_to_z3(left.when, variables, ontology, indices))
            base.add(_expression_to_z3(right.when, variables, ontology, indices))
            status = base.check()
            if status == z3.unknown:
                raise GuidelineValidationError(
                    f"guideline {guideline.id!r} conflict validation incomplete: "
                    f"{base.reason_unknown()}"
                )
            if status == z3.sat:
                model = base.model()
                witness = {
                    item.id: item.allowed_values[
                        model.eval(variables[item.id], model_completion=True).as_long()
                    ]
                    for item in ontology.predicates
                }
                raise GuidelineValidationError(
                    f"guideline {guideline.id!r} has conflicting clauses "
                    f"{sorted([left.id, right.id])} at priority {left.priority}; "
                    f"SMT witness state={witness}"
                )
            base.pop()
