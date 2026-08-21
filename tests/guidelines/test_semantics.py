from __future__ import annotations

from g2lc.guidelines.ast import And, Equals, Known, Not, Or
from g2lc.guidelines.evaluator import (
    DecisionContext,
    EvaluationStatus,
    evaluate_expression,
    evaluate_guideline,
)
from g2lc.guidelines.trivalued import TriValue, tri_and, tri_or
from g2lc.types import EvidenceState


def test_true_and_unknown_is_unknown() -> None:
    assert tri_and([TriValue.TRUE, TriValue.UNKNOWN]) is TriValue.UNKNOWN


def test_false_and_unknown_is_false() -> None:
    assert tri_and([TriValue.FALSE, TriValue.UNKNOWN]) is TriValue.FALSE


def test_true_or_unknown_is_true() -> None:
    assert tri_or([TriValue.TRUE, TriValue.UNKNOWN]) is TriValue.TRUE


def test_false_or_unknown_is_unknown() -> None:
    assert tri_or([TriValue.FALSE, TriValue.UNKNOWN]) is TriValue.UNKNOWN


def test_not_unknown_is_unknown() -> None:
    assert ~TriValue.UNKNOWN is TriValue.UNKNOWN


def test_comparison_with_unknown_is_unknown(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    expression = Equals(predicate="ma_presence", value="present")
    assert (
        evaluate_expression(expression, EvidenceState(values={}), minimal_problem.ontology)
        is TriValue.UNKNOWN
    )


def test_known_missing_is_false(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    expression = Known(predicate="ma_presence")
    assert (
        evaluate_expression(expression, EvidenceState(values={}), minimal_problem.ontology)
        is TriValue.FALSE
    )


def test_and_short_circuit_semantics_not_python_short_circuit(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    expression = And(
        terms=[
            Equals(predicate="gradable", value="no"),
            Equals(predicate="ma_presence", value="present"),
        ]
    )
    state = EvidenceState(values={"gradable": "yes"})
    assert evaluate_expression(expression, state, minimal_problem.ontology) is TriValue.FALSE


def test_or_true_dominates_unknown(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    expression = Or(
        terms=[
            Equals(predicate="gradable", value="yes"),
            Equals(predicate="ma_presence", value="present"),
        ]
    )
    state = EvidenceState(values={"gradable": "yes"})
    assert evaluate_expression(expression, state, minimal_problem.ontology) is TriValue.TRUE


def test_nested_not(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    expression = Not(term=Equals(predicate="gradable", value="no"))
    state = EvidenceState(values={"gradable": "yes"})
    assert evaluate_expression(expression, state, minimal_problem.ontology) is TriValue.TRUE


def test_partial_state_returns_all_possible_completion_actions(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0]
    result = evaluate_guideline(
        guideline,
        EvidenceState(values={"gradable": "yes"}),
        DecisionContext(minimal_problem.ontology, minimal_problem.graph),
    )
    assert result.status is EvaluationStatus.ACTION_SET
    assert {item.values["decision"] for item in result.actions} == {
        "monitor",
        "refer",
        "routine",
    }


def test_ungradable_priority_wins(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    state = EvidenceState(
        values={
            "gradable": "no",
            "ma_presence": "present",
            "hem_count_bin": "4_plus",
            "nv_presence": "present",
        }
    )
    result = evaluate_guideline(
        minimal_problem.guidelines[1],
        state,
        DecisionContext(minimal_problem.ontology, minimal_problem.graph),
    )
    assert result.status is EvaluationStatus.UNIQUE_ACTION
    assert result.actions[0].values == {"decision": "reshoot"}


def test_complete_default_action(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    state = EvidenceState(
        values={
            "gradable": "yes",
            "ma_presence": "absent",
            "hem_count_bin": "0",
            "nv_presence": "absent",
        }
    )
    result = evaluate_guideline(
        minimal_problem.guidelines[0],
        state,
        DecisionContext(minimal_problem.ontology, minimal_problem.graph),
    )
    assert result.status is EvaluationStatus.UNIQUE_ACTION
    assert result.actions[0].values["decision"] == "routine"
