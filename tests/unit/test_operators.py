from __future__ import annotations

import pytest

from g2lc.errors import OperatorValidationError
from g2lc.operators.derivation import distinguishes, exact_observed_predicates
from g2lc.operators.lattice import derivation_closure, validate_operators
from g2lc.operators.models import DerivationGraph, DerivationRule
from g2lc.types import EvidenceState


def test_catalogue_has_required_fixture_operators(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    assert "hem_full_mask" in minimal_problem.catalogue.operator_map()
    assert "image_level_grade" in minimal_problem.catalogue.operator_map()


def test_presence_mapping_does_not_separate_count_bins(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    operator = minimal_problem.catalogue.operator_map()["hem_presence_label"]
    left = EvidenceState(values={"hem_count_bin": "1_3"})
    right = EvidenceState(values={"hem_count_bin": "4_plus"})
    assert not distinguishes(operator, minimal_problem.graph, left, right)


def test_count_bin_separates_count_bins(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    operator = minimal_problem.catalogue.operator_map()["hem_count_bin_label"]
    left = EvidenceState(values={"hem_count_bin": "1_3"})
    right = EvidenceState(values={"hem_count_bin": "4_plus"})
    assert distinguishes(operator, minimal_problem.graph, left, right)


def test_mapped_output_does_not_seed_exact_derivation(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    operator = minimal_problem.catalogue.operator_map()["hem_presence_label"]
    assert "hem_count_bin" not in exact_observed_predicates([operator], minimal_problem.graph)


def test_full_mask_derives_count_bin(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    operator = minimal_problem.catalogue.operator_map()["hem_full_mask"]
    assert "hem_count_bin" in exact_observed_predicates([operator], minimal_problem.graph)


def test_derivation_closure_reaches_fixed_point(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    provenance = minimal_problem.graph.provenance
    graph = DerivationGraph(
        schema_version="1.0",
        graph_id="test",
        version="1",
        provenance=provenance,
        rules=[
            DerivationRule(
                id="a_to_b",
                input_predicates=["gradable"],
                output_predicates=["ma_presence"],
                provenance=provenance,
            ),
            DerivationRule(
                id="b_to_c",
                input_predicates=["ma_presence"],
                output_predicates=["nv_presence"],
                provenance=provenance,
            ),
        ],
    )
    assert derivation_closure({"gradable"}, graph) == {"gradable", "ma_presence", "nv_presence"}


def test_cyclic_derivation_graph_is_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    provenance = minimal_problem.graph.provenance
    graph = DerivationGraph(
        schema_version="1.0",
        graph_id="cycle",
        version="1",
        provenance=provenance,
        rules=[
            DerivationRule(
                id="a_to_b",
                input_predicates=["gradable"],
                output_predicates=["ma_presence"],
                provenance=provenance,
            ),
            DerivationRule(
                id="b_to_a",
                input_predicates=["ma_presence"],
                output_predicates=["gradable"],
                provenance=provenance,
            ),
        ],
    )
    with pytest.raises(OperatorValidationError, match="cyclic"):
        validate_operators(minimal_problem.catalogue, graph, minimal_problem.ontology)


def test_mapping_must_cover_domain(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    operator = minimal_problem.catalogue.operator_map()["hem_presence_label"].model_copy(
        update={"value_mappings": {"hem_count_bin": {"0": "absent"}}}
    )
    catalogue = minimal_problem.catalogue.model_copy(update={"operators": [operator]})
    with pytest.raises(OperatorValidationError, match="entire domain"):
        validate_operators(catalogue, minimal_problem.graph, minimal_problem.ontology)
