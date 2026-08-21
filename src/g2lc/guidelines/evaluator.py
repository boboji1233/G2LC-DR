"""Three-valued expression and prioritized guideline evaluation."""

from __future__ import annotations

from dataclasses import dataclass
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
    guideline_predicates,
)
from g2lc.guidelines.trivalued import TriValue, tri_and, tri_or
from g2lc.ontology.feasibility import feasible_completions
from g2lc.ontology.models import (
    AtMostOneConstraint,
    ConditionalAllowedConstraint,
    DerivedEqualityConstraint,
    EvidenceOntology,
    ExactlyOneConstraint,
    ImplicationConstraint,
    MutualExclusionConstraint,
    ParentChildConstraint,
)
from g2lc.operators.derivation import derivations_consistent
from g2lc.operators.models import DerivationGraph
from g2lc.types import EvidenceState, Modality, StrictModel, scalar_equal
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


@dataclass(frozen=True)
class DecisionContext:
    """Formal decision environment shared by complete and partial evaluation."""

    ontology: EvidenceOntology
    derivations: DerivationGraph | None = None
    target_modalities: tuple[Modality, ...] = ()
    semantic_contract_version: str = "action-only-decision-sufficiency-v1.1"


_DERIVATIONS_UNSET = object()


def _constraint_predicates(constraint: object) -> set[str]:
    if isinstance(constraint, ImplicationConstraint):
        return {constraint.antecedent.predicate, constraint.consequent.predicate}
    if isinstance(
        constraint, (MutualExclusionConstraint, ExactlyOneConstraint, AtMostOneConstraint)
    ):
        return {item.predicate for item in constraint.conditions}
    if isinstance(constraint, ConditionalAllowedConstraint):
        return {constraint.antecedent.predicate, constraint.predicate}
    if isinstance(constraint, DerivedEqualityConstraint):
        return {constraint.source_predicate, constraint.target_predicate}
    if isinstance(constraint, ParentChildConstraint):
        return {constraint.parent_predicate, constraint.child_predicate}
    raise AssertionError(type(constraint).__name__)


def decision_relevant_predicates(
    guideline: Guideline,
    context: DecisionContext,
) -> set[str]:
    """Close guideline predicates over feasibility and deterministic derivations."""

    relevant = set(guideline_predicates(guideline))
    changed = True
    while changed:
        changed = False
        for constraint in context.ontology.feasibility.constraints:
            dependencies = _constraint_predicates(constraint)
            if relevant.intersection(dependencies) and not dependencies.issubset(relevant):
                relevant.update(dependencies)
                changed = True
        if context.derivations is not None:
            for rule in context.derivations.rules:
                dependencies = set(rule.input_predicates) | set(rule.output_predicates)
                if relevant.intersection(dependencies) and not dependencies.issubset(relevant):
                    relevant.update(dependencies)
                    changed = True
    return relevant


def decision_relevant_completions(
    guideline: Guideline,
    state: EvidenceState,
    context: DecisionContext,
) -> list[EvidenceState]:
    """Return one feasible witness per decision-relevant partial completion.

    Unrelated ontology dimensions remain existentially quantified.  They are still
    checked for global feasibility, but they cannot multiply the action evaluation
    work or alter its decision signature.
    """

    relevant = decision_relevant_predicates(guideline, context)
    predicates = context.ontology.predicate_map()
    missing = sorted(item for item in relevant if not state.known(item))
    if not missing:
        witness = next(
            feasible_completions(state, context.ontology, context.derivations),
            None,
        )
        return [witness] if witness is not None else []

    from itertools import product

    witnesses: list[EvidenceState] = []
    for values in product(*(predicates[item].allowed_values for item in missing)):
        partial = EvidenceState(values={**state.values, **dict(zip(missing, values, strict=True))})
        witness = next(
            feasible_completions(partial, context.ontology, context.derivations),
            None,
        )
        if witness is not None:
            witnesses.append(witness)
    return witnesses


def validate_evidence_state(state: EvidenceState, ontology: EvidenceOntology) -> None:
    """Reject unknown keys and values outside their exact typed finite domains."""

    predicates = ontology.predicate_map()
    unknown = sorted(set(state.values) - predicates.keys())
    if unknown:
        raise GuidelineValidationError(f"state has unknown predicate keys: {unknown}")
    for predicate_id, value in state.values.items():
        if value is None:
            continue
        predicate = predicates[predicate_id]
        if not any(scalar_equal(value, allowed) for allowed in predicate.allowed_values):
            raise GuidelineValidationError(
                f"predicate {predicate_id!r} has invalid typed state value {value!r}; "
                f"allowed={predicate.allowed_values!r}"
            )


def evaluate_expression(
    expression: Expression,
    state: EvidenceState,
    ontology: EvidenceOntology,
) -> TriValue:
    """Evaluate one expression without converting unknown evidence to false."""

    validate_evidence_state(state, ontology)
    return _evaluate_expression(expression, state, ontology)


def _evaluate_expression(
    expression: Expression,
    state: EvidenceState,
    ontology: EvidenceOntology,
) -> TriValue:
    """Internal expression evaluator for an already validated state."""

    predicates = ontology.predicate_map()
    if isinstance(expression, (And, Or)):
        values = [_evaluate_expression(term, state, ontology) for term in expression.terms]
        return tri_and(values) if isinstance(expression, And) else tri_or(values)
    if isinstance(expression, Not):
        return ~_evaluate_expression(expression.term, state, ontology)
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
        return TriValue.TRUE if scalar_equal(value, expression.value) else TriValue.FALSE
    if isinstance(expression, InSet):
        return (
            TriValue.TRUE
            if any(scalar_equal(value, candidate) for candidate in expression.values)
            else TriValue.FALSE
        )
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
    context: DecisionContext | EvidenceOntology,
    *,
    derivations: DerivationGraph | object | None = _DERIVATIONS_UNSET,
) -> GuidelineEvaluation:
    """Evaluate priorities under an explicit feasibility/derivation context.

    Passing a bare ontology without the keyword-only ``derivations`` declaration is
    rejected.  That compatibility boundary prevents the pre-Stage-1.6 failure mode in
    which a caller silently forgot a project's deterministic derivation graph.
    """

    if isinstance(context, DecisionContext):
        if derivations is not _DERIVATIONS_UNSET:
            raise GuidelineValidationError(
                "do not pass derivations separately when using DecisionContext"
            )
        decision_context = context
    else:
        if derivations is _DERIVATIONS_UNSET:
            raise GuidelineValidationError(
                "evaluate_guideline requires DecisionContext or an explicit "
                "derivations=None declaration"
            )
        if derivations is not None and not isinstance(derivations, DerivationGraph):
            raise GuidelineValidationError("invalid derivation context")
        decision_context = DecisionContext(
            ontology=context,
            derivations=derivations,
        )
    ontology = decision_context.ontology
    derivation_graph = decision_context.derivations

    results: list[tuple[int, str, ClinicalAction, TriValue]] = []
    try:
        validate_evidence_state(state, ontology)
        for rule in guideline.rules:
            results.append(
                (
                    rule.priority,
                    rule.id,
                    rule.action,
                    _evaluate_expression(rule.when, state, ontology),
                )
            )
    except OutOfSpecificationError as exc:
        message = str(exc)
        predicate = message.split("'")[1] if "'" in message else message
        return GuidelineEvaluation(
            status=EvaluationStatus.OUT_OF_SPEC,
            unsupported_predicates=[predicate],
        )

    missing = [item.id for item in ontology.predicates if not state.known(item.id)]
    action_by_key: dict[str, ClinicalAction] = {}
    matched: set[str] = set()
    if missing:
        for complete in decision_relevant_completions(guideline, state, decision_context):
            actions, winner_ids = _evaluate_complete(guideline, complete, ontology)
            matched.update(winner_ids)
            for action in actions:
                action_by_key[canonical_json(action.model_dump(mode="json"))] = action
    else:
        if derivation_graph is not None and not derivations_consistent(state, derivation_graph):
            raise GuidelineValidationError(
                "complete evidence state is inconsistent with deterministic derivations"
            )
        actions, winner_ids = _evaluate_complete(guideline, state, ontology)
        matched.update(winner_ids)
        for action in actions:
            action_by_key[canonical_json(action.model_dump(mode="json"))] = action

    actions = [action_by_key[key] for key in sorted(action_by_key)]
    unknown = sorted(item[1] for item in results if item[3] is TriValue.UNKNOWN)
    status = EvaluationStatus.INSUFFICIENT_EVIDENCE
    if len(actions) == 1:
        status = EvaluationStatus.UNIQUE_ACTION
    elif len(actions) > 1:
        status = EvaluationStatus.ACTION_SET
    return GuidelineEvaluation(
        status=status,
        actions=actions,
        matched_clauses=sorted(matched),
        unknown_clauses=unknown,
    )


def _evaluate_complete(
    guideline: Guideline,
    state: EvidenceState,
    ontology: EvidenceOntology,
) -> tuple[list[ClinicalAction], list[str]]:
    """Evaluate a state complete for every predicate referenced by a guideline."""

    true_rules = [
        rule
        for rule in guideline.rules
        if _evaluate_expression(rule.when, state, ontology) is TriValue.TRUE
    ]
    if not true_rules:
        return ([guideline.default_action] if guideline.default_action is not None else []), []
    highest = max(rule.priority for rule in true_rules)
    winners = sorted((rule for rule in true_rules if rule.priority == highest), key=lambda x: x.id)
    by_key = {canonical_json(rule.action.model_dump(mode="json")): rule.action for rule in winners}
    return [by_key[key] for key in sorted(by_key)], [rule.id for rule in winners]


def decision_signature(evaluation: GuidelineEvaluation) -> str:
    """Canonicalize only the normalized possible action set."""

    actions = sorted(
        (item.model_dump(mode="json") for item in evaluation.actions),
        key=canonical_json,
    )
    return canonical_json(actions)


def trace_signature(evaluation: GuidelineEvaluation) -> str:
    """Canonicalize the full result for audit only, never pair generation."""

    return canonical_json(evaluation.model_dump(mode="json"))


def action_signature(evaluation: GuidelineEvaluation) -> str:
    """Backward-compatible name for the action-only decision signature."""

    return decision_signature(evaluation)
