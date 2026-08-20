from __future__ import annotations

import pytest

from g2lc.errors import GuidelineValidationError, SourceValidationError
from g2lc.guidelines.ast import Equals
from g2lc.guidelines.parser import load_guidelines
from g2lc.guidelines.validator import validate_guidelines


def test_bundle_is_explicitly_synthetic(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    assert minimal_problem.guideline_bundles[0].synthetic is True


def test_all_clauses_have_provenance(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    assert all(rule.provenance.source for item in minimal_problem.guidelines for rule in item.rules)


def test_out_of_domain_comparison_is_actionable(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0]
    bad_rule = guideline.rules[0].model_copy(
        update={"when": Equals(predicate="gradable", value="maybe")}
    )
    bad_guideline = guideline.model_copy(update={"rules": [bad_rule, *guideline.rules[1:]]})
    bundle = minimal_problem.guideline_bundles[0].model_copy(update={"guidelines": [bad_guideline]})
    with pytest.raises(GuidelineValidationError, match="out-of-domain"):
        validate_guidelines(bundle, minimal_problem.ontology)


def test_clause_version_must_match(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0]
    provenance = guideline.rules[0].provenance.model_copy(update={"version": "other"})
    rule = guideline.rules[0].model_copy(update={"provenance": provenance})
    changed = guideline.model_copy(update={"rules": [rule, *guideline.rules[1:]]})
    bundle = minimal_problem.guideline_bundles[0].model_copy(update={"guidelines": [changed]})
    with pytest.raises(GuidelineValidationError, match="does not match"):
        validate_guidelines(bundle)


def test_malformed_dsl_reports_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: '1.0'\nguidelines: []\n", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="guidelines"):
        load_guidelines(path)


def test_conflicting_same_priority_rules_are_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    guideline = minimal_problem.guidelines[0]
    first = guideline.rules[1]
    second = guideline.rules[2].model_copy(update={"priority": first.priority, "when": first.when})
    changed = guideline.model_copy(update={"rules": [first, second]})
    bundle = minimal_problem.guideline_bundles[0].model_copy(update={"guidelines": [changed]})
    with pytest.raises(GuidelineValidationError, match="conflicting clauses"):
        validate_guidelines(bundle, minimal_problem.ontology)
