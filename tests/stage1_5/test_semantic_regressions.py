from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import g2lc.compiler.counterexample as separation_module
from g2lc.certificates.writer import build_certificate
from g2lc.compiler.api import compile_problem
from g2lc.compiler.result import SolverKind, SolverStatus
from g2lc.errors import GuidelineValidationError, OperatorValidationError
from g2lc.guidelines.ast import ClinicalAction, Equals
from g2lc.guidelines.evaluator import (
    EvaluationStatus,
    action_signature,
    evaluate_expression,
    evaluate_guideline,
)
from g2lc.guidelines.validator import validate_guidelines
from g2lc.operators.lattice import validate_operators
from g2lc.operators.models import DerivationGraph, DerivationRule
from g2lc.types import EvidenceState, ValueType


def test_same_action_different_trace_has_same_decision_signature(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0]
    provenance = guideline.rules[0].provenance
    action = ClinicalAction(values={"decision": "monitor"})
    high = guideline.rules[0].model_copy(
        update={
            "id": "ma_monitor",
            "priority": 80,
            "when": Equals(predicate="ma_presence", value="present"),
            "action": action,
            "provenance": provenance,
        }
    )
    low = guideline.rules[1].model_copy(
        update={
            "id": "hem_monitor",
            "priority": 60,
            "when": Equals(predicate="hem_count_bin", value="1_3"),
            "action": action,
            "provenance": provenance,
        }
    )
    changed = guideline.model_copy(update={"rules": [high, low]})
    left = EvidenceState(
        values={
            "gradable": "yes",
            "ma_presence": "present",
            "hem_count_bin": "0",
            "nv_presence": "absent",
        }
    )
    right = EvidenceState(
        values={
            "gradable": "yes",
            "ma_presence": "absent",
            "hem_count_bin": "1_3",
            "nv_presence": "absent",
        }
    )

    left_result = evaluate_guideline(changed, left, minimal_problem.ontology)
    right_result = evaluate_guideline(changed, right, minimal_problem.ontology)

    assert left_result.matched_clauses != right_result.matched_clauses
    assert action_signature(left_result) == action_signature(right_result)


def test_default_same_action_as_rule_has_same_decision_signature(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0]
    rule = guideline.rules[0]
    changed = guideline.model_copy(update={"default_action": rule.action, "rules": [rule]})
    rule_state = EvidenceState(
        values={
            "gradable": "no",
            "ma_presence": "absent",
            "hem_count_bin": "0",
            "nv_presence": "absent",
        }
    )
    default_state = EvidenceState(
        values={
            "gradable": "yes",
            "ma_presence": "absent",
            "hem_count_bin": "0",
            "nv_presence": "absent",
        }
    )

    rule_result = evaluate_guideline(changed, rule_state, minimal_problem.ontology)
    default_result = evaluate_guideline(changed, default_state, minimal_problem.ontology)

    assert rule_result.matched_clauses != default_result.matched_clauses
    assert action_signature(rule_result) == action_signature(default_result)


def test_higher_unknown_rule_preserves_possible_action(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[1]
    provenance = guideline.rules[0].provenance
    high = guideline.rules[1].model_copy(
        update={
            "id": "unknown_high",
            "priority": 100,
            "when": Equals(predicate="nv_presence", value="present"),
            "action": ClinicalAction(values={"decision": "urgent"}),
            "provenance": provenance,
        }
    )
    low = guideline.rules[0].model_copy(
        update={
            "id": "known_low",
            "priority": 50,
            "when": Equals(predicate="gradable", value="yes"),
            "action": ClinicalAction(values={"decision": "monitor"}),
            "provenance": provenance,
        }
    )
    changed = guideline.model_copy(update={"rules": [high, low]})

    result = evaluate_guideline(
        changed,
        EvidenceState(values={"gradable": "yes"}),
        minimal_problem.ontology,
    )

    assert result.status is EvaluationStatus.ACTION_SET
    assert {item.values["decision"] for item in result.actions} == {"monitor", "urgent"}


def test_action_schema_requires_all_and_only_declared_keys(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0].model_copy(
        update={"action_schema": ["decision", "timing"]}
    )
    bundle = minimal_problem.guideline_bundles[0].model_copy(update={"guidelines": [guideline]})

    with pytest.raises(GuidelineValidationError, match="exactly match"):
        validate_guidelines(bundle, minimal_problem.ontology)


def test_bool_and_int_are_distinct_at_evaluation_boundary(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    predicate = minimal_problem.ontology.predicates[0].model_copy(
        update={"value_type": ValueType.BOOLEAN, "allowed_values": [False, True]}
    )
    ontology = minimal_problem.ontology.model_copy(update={"predicates": [predicate]})

    with pytest.raises(GuidelineValidationError, match="state value"):
        evaluate_expression(
            Equals(predicate="gradable", value=True),
            EvidenceState(values={"gradable": 1}),
            ontology,
        )


def test_unknown_state_key_is_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(GuidelineValidationError, match="unknown predicate"):
        evaluate_guideline(
            minimal_problem.guidelines[0],
            EvidenceState(values={"not_declared": "value"}),
            minimal_problem.ontology,
        )


def test_non_synthetic_guideline_requires_iso_effective_date(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    bundle = minimal_problem.guideline_bundles[0].model_copy(update={"synthetic": False})

    with pytest.raises(GuidelineValidationError, match="ISO"):
        validate_guidelines(bundle, minimal_problem.ontology)


def test_multi_input_derivation_is_rejected_until_soundly_encoded(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    graph = DerivationGraph(
        schema_version="1.1",
        graph_id="multi_input_unsound",
        version="1.1.0-synthetic",
        provenance=minimal_problem.graph.provenance,
        rules=[
            DerivationRule(
                id="multi_input",
                input_predicates=["gradable", "ma_presence"],
                output_predicates=["nv_presence"],
                provenance=minimal_problem.graph.provenance,
            )
        ],
    )

    with pytest.raises(OperatorValidationError, match="unary"):
        validate_operators(minimal_problem.catalogue, graph, minimal_problem.ontology)


def test_separation_does_not_promote_feasible_master_to_optimal(
    minimal_problem: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = [item.id for item in minimal_problem.available_operators()]
    monkeypatch.setattr(
        separation_module,
        "_solve_master",
        lambda *_args, **_kwargs: (selected, SolverStatus.FEASIBLE),
    )
    monkeypatch.setattr(
        separation_module,
        "find_counterexample",
        lambda *_args, **_kwargs: None,
    )

    solution = separation_module.solve_counterexample_separation(minimal_problem)

    assert solution.solver_status is SolverStatus.FEASIBLE
    assert solution.optimal is False


def test_certificate_uses_semantic_schema_1_1(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    solution = compile_problem(minimal_problem, SolverKind.EXACT)
    certificate = build_certificate(minimal_problem, solution)
    payload = certificate.model_dump(mode="json")

    assert payload["schema_version"] == "1.1"
    assert payload["semantic_contract"] == "action-only-decision-sufficiency-v1.1"
    assert payload["proof_scope"] in {"FINITE_EXHAUSTIVE", "SMT_UNIVERSAL", "BOUNDED"}
    assert payload["objective_tuple"][1] == len(payload["selected_operators"])


def test_independent_verifier_package_has_no_compiler_imports() -> None:
    package = Path("src/g2lc_verifier")
    assert package.is_dir()
    sources = "\n".join(path.read_text(encoding="utf-8") for path in package.rglob("*.py"))
    assert "g2lc.compiler" not in sources
    assert "g2lc.certificates.writer" not in sources
