"""Guideline semantic validation against an evidence ontology."""

from __future__ import annotations

import itertools
import math

from g2lc.errors import GuidelineValidationError
from g2lc.guidelines.ast import (
    And,
    Equals,
    Expression,
    GreaterEqual,
    Guideline,
    GuidelineBundle,
    InSet,
    LessEqual,
    Not,
    Or,
    expression_predicates,
)
from g2lc.guidelines.evaluator import evaluate_expression
from g2lc.guidelines.trivalued import TriValue
from g2lc.ontology.models import EvidenceOntology
from g2lc.types import EvidenceState, ReviewStatus, ValueType
from g2lc.utils.io import canonical_json


def validate_guidelines(
    bundle: GuidelineBundle,
    ontology: EvidenceOntology | None = None,
    *,
    conflict_state_limit: int = 10_000,
) -> None:
    """Validate provenance, action shape, predicate types and finite conflicts."""

    for guideline in bundle.guidelines:
        _validate_guideline(guideline, bundle.synthetic, ontology, conflict_state_limit)


def _validate_guideline(
    guideline: Guideline,
    bundle_synthetic: bool,
    ontology: EvidenceOntology | None,
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
    for rule in guideline.rules:
        if rule.provenance.version != guideline.version:
            raise GuidelineValidationError(
                f"clause {guideline.id}.{rule.id} provenance version does not match guideline"
            )
        if bundle_synthetic and rule.provenance.review_status is not ReviewStatus.SYNTHETIC:
            raise GuidelineValidationError(
                f"synthetic clause {guideline.id}.{rule.id} must use SYNTHETIC review_status"
            )
        unknown_keys = sorted(set(rule.action.values) - schema)
        if unknown_keys:
            raise GuidelineValidationError(
                f"clause {guideline.id}.{rule.id} has action keys outside schema: {unknown_keys}"
            )
    if guideline.default_action is not None:
        unknown_keys = sorted(set(guideline.default_action.values) - schema)
        if unknown_keys:
            raise GuidelineValidationError(
                f"guideline {guideline.id!r} default action keys outside schema: {unknown_keys}"
            )
    if ontology is None:
        return
    for rule in guideline.rules:
        _validate_expression(rule.when, ontology, f"{guideline.id}.{rule.id}")
    relevant = sorted(set().union(*(expression_predicates(rule.when) for rule in guideline.rules)))
    state_count = math.prod(len(ontology.predicate(item).allowed_values) for item in relevant)
    if state_count <= conflict_state_limit:
        _reject_same_priority_conflicts(guideline, ontology, relevant)


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
        if expression.value not in predicate.allowed_values:
            raise GuidelineValidationError(
                f"clause {context} compares {predicate.id!r} to out-of-domain value "
                f"{expression.value!r}"
            )
    elif isinstance(expression, InSet):
        invalid = [value for value in expression.values if value not in predicate.allowed_values]
        if invalid:
            raise GuidelineValidationError(
                f"clause {context} uses out-of-domain values {invalid} for {predicate.id!r}"
            )


def _reject_same_priority_conflicts(
    guideline: Guideline,
    ontology: EvidenceOntology,
    relevant: list[str],
) -> None:
    domains = [ontology.predicate(item).allowed_values for item in relevant]
    for values in itertools.product(*domains):
        state = EvidenceState(values=dict(zip(relevant, values, strict=True)))
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
