from __future__ import annotations

import pytest
from pydantic import ValidationError

from g2lc.errors import OntologyValidationError
from g2lc.ontology.models import EvidencePredicate
from g2lc.ontology.observability import find_observability_issues
from g2lc.ontology.validator import validate_ontology
from g2lc.types import Modality


def test_minimal_ontology_loads(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    assert minimal_problem.ontology.ontology_id == "synthetic_minimal_dr_evidence"
    assert sorted(minimal_problem.ontology.predicate_map()) == [
        "gradable",
        "hem_count_bin",
        "ma_presence",
        "nv_presence",
    ]


def test_predicate_domain_rejects_unknown(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    raw = minimal_problem.ontology.predicates[0].model_dump(mode="python")
    raw["allowed_values"] = ["yes", None]
    with pytest.raises(ValidationError, match="UNKNOWN"):
        EvidencePredicate.model_validate(raw)


def test_boolean_domain_is_typed(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    raw = minimal_problem.ontology.predicates[0].model_dump(mode="python")
    raw["value_type"] = "BOOLEAN"
    with pytest.raises(ValidationError, match="booleans"):
        EvidencePredicate.model_validate(raw)


def test_unknown_requirement_is_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    predicate = minimal_problem.ontology.predicates[1].model_copy(update={"requires": ["missing"]})
    ontology = minimal_problem.ontology.model_copy(
        update={"predicates": [minimal_problem.ontology.predicates[0], predicate]}
    )
    with pytest.raises(OntologyValidationError, match="unknown predicates"):
        validate_ontology(ontology)


def test_self_requirement_is_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    predicate = minimal_problem.ontology.predicates[0].model_copy(update={"requires": ["gradable"]})
    ontology = minimal_problem.ontology.model_copy(update={"predicates": [predicate]})
    with pytest.raises(OntologyValidationError, match="references itself"):
        validate_ontology(ontology)


def test_dependency_cycle_is_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    first = minimal_problem.ontology.predicates[0].model_copy(update={"requires": ["ma_presence"]})
    second = minimal_problem.ontology.predicates[1].model_copy(update={"requires": ["gradable"]})
    ontology = minimal_problem.ontology.model_copy(update={"predicates": [first, second]})
    with pytest.raises(OntologyValidationError, match="cycle"):
        validate_ontology(ontology)


def test_cfp_oct_predicate_is_oos(oos_problem) -> None:  # type: ignore[no-untyped-def]
    issues = find_observability_issues(
        oos_problem.ontology, {"oct_central_thickness"}, {Modality.CFP}
    )
    assert issues[0].required_modalities == ("OCT",)


def test_unknown_predicate_is_oos(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    issues = find_observability_issues(minimal_problem.ontology, {"visual_acuity"}, {Modality.CFP})
    assert issues[0].predicate_id == "visual_acuity"
    assert issues[0].required_modalities == ()
