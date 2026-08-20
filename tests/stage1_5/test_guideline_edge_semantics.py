from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import z3
from pydantic import ValidationError

from g2lc.errors import GuidelineValidationError, SourceValidationError
from g2lc.guidelines.ast import (
    And,
    ClinicalAction,
    Equals,
    Expression,
    GreaterEqual,
    GuidelineBundle,
    InSet,
    Known,
    LessEqual,
    Not,
    Or,
    expression_predicates,
)
from g2lc.guidelines.evaluator import (
    EvaluationStatus,
    evaluate_expression,
    evaluate_guideline,
    trace_signature,
)
from g2lc.guidelines.parser import _expression, _normalize, load_guidelines
from g2lc.guidelines.provenance import clause_hash, guideline_hash
from g2lc.guidelines.trivalued import TriValue
from g2lc.guidelines.validator import _expression_to_z3, validate_guidelines
from g2lc.types import EvidenceState, ReviewStatus


def test_guideline_ast_rejects_ambiguous_and_duplicate_shapes(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError, match="Known"):
        Equals(predicate="gradable", value=None)
    with pytest.raises(ValidationError, match="UNKNOWN"):
        InSet(predicate="gradable", values=[None])
    with pytest.raises(ValidationError, match="unique"):
        InSet(predicate="gradable", values=["yes", "yes"])
    with pytest.raises(ValidationError, match="nonempty"):
        ClinicalAction(values={"decision": ""})

    guideline = minimal_problem.guidelines[0]
    with pytest.raises(ValidationError, match="action_schema"):
        guideline.model_validate({**guideline.model_dump(), "action_schema": ["d", "d"]})
    duplicate_rule = guideline.model_dump()
    duplicate_rule["rules"] = [duplicate_rule["rules"][0], duplicate_rule["rules"][0]]
    with pytest.raises(ValidationError, match="duplicate clause"):
        guideline.model_validate(duplicate_rule)
    bundle = minimal_problem.guideline_bundles[0].model_dump()
    bundle["guidelines"] = [bundle["guidelines"][0], bundle["guidelines"][0]]
    with pytest.raises(ValidationError, match="duplicate guideline"):
        GuidelineBundle.model_validate(bundle)

    nested = And(
        terms=[
            Or(terms=[Known(predicate="gradable"), Known(predicate="ma_presence")]),
            Not(term=Known(predicate="nv_presence")),
        ]
    )
    assert expression_predicates(nested) == {"gradable", "ma_presence", "nv_presence"}


def test_evaluator_numeric_oos_empty_and_trace_paths(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    ontology = minimal_problem.ontology
    assert (
        evaluate_expression(
            InSet(predicate="gradable", values=["yes"]),
            EvidenceState(values={"gradable": "no"}),
            ontology,
        )
        is TriValue.FALSE
    )
    numeric_predicate = ontology.predicates[0].model_copy(
        update={"value_type": "INTEGER", "allowed_values": [1, 2]}
    )
    numeric_ontology = ontology.model_copy(update={"predicates": [numeric_predicate]})
    assert (
        evaluate_expression(
            GreaterEqual(predicate="gradable", value=2),
            EvidenceState(values={"gradable": 2}),
            numeric_ontology,
        )
        is TriValue.TRUE
    )
    assert (
        evaluate_expression(
            LessEqual(predicate="gradable", value=1),
            EvidenceState(values={"gradable": 2}),
            numeric_ontology,
        )
        is TriValue.FALSE
    )
    with pytest.raises(GuidelineValidationError, match="non-numeric"):
        evaluate_expression(
            GreaterEqual(predicate="gradable", value=1),
            EvidenceState(values={"gradable": True}),
            numeric_ontology.model_copy(
                update={
                    "predicates": [
                        numeric_predicate.model_copy(
                            update={"value_type": "BOOLEAN", "allowed_values": [False, True]}
                        )
                    ]
                }
            ),
        )

    guideline = minimal_problem.guidelines[0]
    unknown_rule = guideline.rules[0].model_copy(
        update={"when": Equals(predicate="outside", value="x")}
    )
    oos = evaluate_guideline(
        guideline.model_copy(update={"rules": [unknown_rule]}),
        EvidenceState(values={}),
        ontology,
    )
    assert oos.status is EvaluationStatus.OUT_OF_SPEC
    assert oos.unsupported_predicates == ["outside"]

    no_default = guideline.model_copy(
        update={"rules": [guideline.rules[0]], "default_action": None}
    )
    complete = EvidenceState(
        values={
            "gradable": "yes",
            "ma_presence": "absent",
            "hem_count_bin": "0",
            "nv_presence": "absent",
        }
    )
    result = evaluate_guideline(no_default, complete, ontology)
    assert result.status is EvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "INSUFFICIENT_EVIDENCE" in trace_signature(result)


def test_source_parser_rejects_every_malformed_operator(tmp_path: Path) -> None:
    with pytest.raises(SourceValidationError, match="one-key"):
        _expression([], "x")
    with pytest.raises(SourceValidationError, match="nonempty"):
        _expression({"all": []}, "x")
    assert _expression({"not": {"known": "a"}}, "x")["op"] == "not"
    with pytest.raises(SourceValidationError, match=r"must be \[predicate, value\]"):
        _expression({"eq": [1]}, "x")
    with pytest.raises(SourceValidationError, match=r"must be \[predicate"):
        _expression({"in": ["a", "bad"]}, "x")
    with pytest.raises(SourceValidationError, match="must name"):
        _expression({"known": 1}, "x")
    with pytest.raises(SourceValidationError, match="unsupported"):
        _expression({"xor": []}, "x")
    with pytest.raises(SourceValidationError, match="top-level"):
        _normalize([])
    with pytest.raises(SourceValidationError, match="rules"):
        _normalize({"guidelines": [{}]})
    with pytest.raises(SourceValidationError, match="requires when and then"):
        _normalize({"guidelines": [{"rules": [{}]}]})

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("schema_version: '1.0'\nsynthetic: true\nguidelines: []\n", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="guidelines"):
        load_guidelines(invalid)


def test_guideline_provenance_hashes_are_semantic(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0]
    assert len(guideline_hash(guideline)) == 64
    assert len(clause_hash(guideline.rules[0])) == 64
    assert guideline_hash(guideline) != guideline_hash(
        guideline.model_copy(update={"effective_date": "different-synthetic-marker"})
    )


def test_validator_rejects_provenance_default_predicate_and_type_errors(
    minimal_problem: Any,
) -> None:
    bundle = minimal_problem.guideline_bundles[0]
    guideline = minimal_problem.guidelines[0]
    bad_version = guideline.model_copy(
        update={"provenance": guideline.provenance.model_copy(update={"version": "bad"})}
    )
    with pytest.raises(GuidelineValidationError, match="provenance version"):
        validate_guidelines(bundle.model_copy(update={"guidelines": [bad_version]}))

    bad_review = guideline.model_copy(
        update={
            "provenance": guideline.provenance.model_copy(
                update={"review_status": ReviewStatus.DRAFT}
            )
        }
    )
    with pytest.raises(GuidelineValidationError, match="SYNTHETIC"):
        validate_guidelines(bundle.model_copy(update={"guidelines": [bad_review]}))

    rule = guideline.rules[0].model_copy(
        update={
            "provenance": guideline.rules[0].provenance.model_copy(
                update={"review_status": ReviewStatus.DRAFT}
            )
        }
    )
    with pytest.raises(GuidelineValidationError, match="synthetic clause"):
        validate_guidelines(
            bundle.model_copy(
                update={"guidelines": [guideline.model_copy(update={"rules": [rule]})]}
            )
        )

    default_bad = guideline.model_copy(
        update={"default_action": ClinicalAction(values={"extra": "x"})}
    )
    with pytest.raises(GuidelineValidationError, match="default action keys"):
        validate_guidelines(bundle.model_copy(update={"guidelines": [default_bad]}))

    unknown = guideline.rules[0].model_copy(update={"when": Equals(predicate="outside", value="x")})
    with pytest.raises(GuidelineValidationError, match="unknown predicate"):
        validate_guidelines(
            bundle.model_copy(
                update={"guidelines": [guideline.model_copy(update={"rules": [unknown]})]}
            ),
            minimal_problem.ontology,
        )

    numeric = guideline.rules[0].model_copy(
        update={"when": GreaterEqual(predicate="gradable", value=1)}
    )
    with pytest.raises(GuidelineValidationError, match="non-numeric"):
        validate_guidelines(
            bundle.model_copy(
                update={"guidelines": [guideline.model_copy(update={"rules": [numeric]})]}
            ),
            minimal_problem.ontology,
        )

    invalid_set = guideline.rules[0].model_copy(
        update={"when": InSet(predicate="gradable", values=["outside"])}
    )
    with pytest.raises(GuidelineValidationError, match="out-of-domain values"):
        validate_guidelines(
            bundle.model_copy(
                update={"guidelines": [guideline.model_copy(update={"rules": [invalid_set]})]}
            ),
            minimal_problem.ontology,
        )


def test_validator_z3_expression_translation_covers_full_language(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    ontology = minimal_problem.ontology
    variables = {item.id: z3.Int(item.id) for item in ontology.predicates}
    indices = {
        item.id: {f"str:{value}": index for index, value in enumerate(item.allowed_values)}
        for item in ontology.predicates
    }
    expressions: list[Expression] = [
        Or(terms=[Equals(predicate="gradable", value="yes")]),
        Not(term=Equals(predicate="gradable", value="no")),
        InSet(predicate="gradable", values=["yes"]),
        Known(predicate="gradable"),
    ]
    assert all(
        z3.is_bool(_expression_to_z3(item, variables, ontology, indices)) for item in expressions
    )

    numeric = ontology.predicates[0].model_copy(
        update={"value_type": "INTEGER", "allowed_values": [1, 2]}
    )
    numeric_ontology = ontology.model_copy(update={"predicates": [numeric]})
    numeric_variables = {"gradable": z3.Int("numeric")}
    numeric_indices = {"gradable": {"int:1": 0, "int:2": 1}}
    assert z3.is_bool(
        _expression_to_z3(
            GreaterEqual(predicate="gradable", value=2),
            numeric_variables,
            numeric_ontology,
            numeric_indices,
        )
    )
    assert z3.is_bool(
        _expression_to_z3(
            LessEqual(predicate="gradable", value=1),
            numeric_variables,
            numeric_ontology,
            numeric_indices,
        )
    )
