"""Three-valued expression and prioritized guideline evaluation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from g2lc.errors import GuidelineValidationError, OutOfSpecificationError
from g2lc.guidelines.ast import (
    And,
    ClinicalAction,
    Equals,
    Expression,
    GreaterEqual,
    Guideline,
    InSet,
    Known,
    LessEqual,
    Not,
    Or,
)
from g2lc.guidelines.trivalued import TriValue, tri_and, tri_or
from g2lc.ontology.models import EvidenceOntology
from g2lc.types import EvidenceState, StrictModel
from g2lc.utils.io import canonical_json


class EvaluationStatus(StrEnum):
    """Possible outcomes of evaluating one guideline."""

    UNIQUE_ACTION = "UNIQUE_ACTION"
    ACTION_SET = "ACTION_SET"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    OUT_OF_SPEC = "OUT_OF_SPEC"


class GuidelineEvaluation(StrictModel):
    """Auditable result with matched and unresolved clauses."""

    status: EvaluationStatus
    actions: list[ClinicalAction] = Field(default_factory=list)
    matched_clauses: list[str] = Field(default_factory=list)
    unknown_clauses: list[str] = Field(default_factory=list)
    unsupported_predicates: list[str] = Field(default_factory=list)


def evaluate_expression(
    expression: Expression,
    state: EvidenceState,
    ontology: EvidenceOntology,
) -> TriValue:
    """Evaluate one expression without converting unknown evidence to false."""

    predicates = ontology.predicate_map()
    if isinstance(expression, (And, Or)):
        values = [evaluate_expression(term, state, ontology) for term in expression.terms]
        return tri_and(values) if isinstance(expression, And) else tri_or(values)
    if isinstance(expression, Not):
        return ~evaluate_expression(expression.term, state, ontology)
    if expression.predicate not in predicates:
        raise OutOfSpecificationError(
            f"predicate {expression.predicate!r} is not declared in ontology "
            f"{ontology.ontology_id!r}"
        )
    value = state.value(expression.predicate)
    if isinstance(expression, Known):
        return TriValue.TRUE if value is not None else TriValue.FALSE
    if value is None:
        return TriValue.UNKNOWN
    if isinstance(expression, Equals):
        return TriValue.TRUE if value == expression.value else TriValue.FALSE
    if isinstance(expression, InSet):
        return TriValue.TRUE if value in expression.values else TriValue.FALSE
    if isinstance(expression, (GreaterEqual, LessEqual)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GuidelineValidationError(
                f"predicate {expression.predicate!r} has non-numeric state value {value!r}"
            )
        if isinstance(expression, GreaterEqual):
            return TriValue.TRUE if value >= expression.value else TriValue.FALSE
        return TriValue.TRUE if value <= expression.value else TriValue.FALSE
    raise AssertionError(f"unhandled expression {type(expression).__name__}")


def evaluate_guideline(
    guideline: Guideline,
    state: EvidenceState,
    ontology: EvidenceOntology,
) -> GuidelineEvaluation:
    """Evaluate priorities while retaining ambiguity and missing evidence."""

    results: list[tuple[int, str, ClinicalAction, TriValue]] = []
    try:
        for rule in guideline.rules:
            results.append(
                (
                    rule.priority,
                    rule.id,
                    rule.action,
                    evaluate_expression(rule.when, state, ontology),
                )
            )
    except OutOfSpecificationError as exc:
        message = str(exc)
        predicate = message.split("'")[1] if "'" in message else message
        return GuidelineEvaluation(
            status=EvaluationStatus.OUT_OF_SPEC,
            unsupported_predicates=[predicate],
        )

    true_rules = [item for item in results if item[3] is TriValue.TRUE]
    if true_rules:
        highest = max(item[0] for item in true_rules)
        winners = sorted(
            (item for item in true_rules if item[0] == highest), key=lambda item: item[1]
        )
        actions_by_key = {
            canonical_json(item[2].model_dump(mode="json")): item[2] for item in winners
        }
        actions = [actions_by_key[key] for key in sorted(actions_by_key)]
        return GuidelineEvaluation(
            status=(
                EvaluationStatus.UNIQUE_ACTION if len(actions) == 1 else EvaluationStatus.ACTION_SET
            ),
            actions=actions,
            matched_clauses=[item[1] for item in winners],
            unknown_clauses=sorted(item[1] for item in results if item[3] is TriValue.UNKNOWN),
        )

    unknown = sorted(item[1] for item in results if item[3] is TriValue.UNKNOWN)
    if unknown:
        return GuidelineEvaluation(
            status=EvaluationStatus.INSUFFICIENT_EVIDENCE,
            unknown_clauses=unknown,
        )
    if guideline.default_action is not None:
        return GuidelineEvaluation(
            status=EvaluationStatus.UNIQUE_ACTION,
            actions=[guideline.default_action],
        )
    return GuidelineEvaluation(status=EvaluationStatus.INSUFFICIENT_EVIDENCE)


def action_signature(evaluation: GuidelineEvaluation) -> str:
    """Canonicalize a full evaluation outcome for state-pair comparison."""

    return canonical_json(evaluation.model_dump(mode="json"))
