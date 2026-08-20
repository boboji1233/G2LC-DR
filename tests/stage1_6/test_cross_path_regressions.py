from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from g2lc.certificates.writer import (
    _portable,
    _repository_root,
    build_certificate,
    write_certificate,
)
from g2lc.compiler.api import compile_problem
from g2lc.compiler.exact import solve_exact
from g2lc.compiler.problem import (
    _constraint_predicates,
    build_finite_problem,
    enumerate_relevant_states,
    enumerate_states,
    load_compiler_problem,
    relevant_predicate_closure,
)
from g2lc.compiler.result import SolverKind
from g2lc.errors import (
    CertificateVerificationError,
    CompilationError,
    GuidelineValidationError,
    OntologyValidationError,
)
from g2lc.guidelines.ast import ClinicalAction, Equals
from g2lc.guidelines.evaluator import evaluate_guideline
from g2lc.guidelines.validator import validate_guidelines
from g2lc.ontology.models import FeasibilityProgram
from g2lc.ontology.validator import validate_ontology
from g2lc.operators.models import DerivationGraph, DerivationRule
from g2lc.types import EvidenceState
from g2lc_verifier import verify_certificate
from g2lc_verifier.verifier import _constraint_predicates as verifier_constraint_predicates
from g2lc_verifier.verifier import _relevant_predicates

REGRESSION_ROOT = Path(__file__).parents[1] / "fixtures" / "regressions" / "generated"


def _ma_only_problem(minimal_problem: Any) -> Any:
    guideline = minimal_problem.guidelines[0]
    rule = guideline.rules[0].model_copy(
        update={
            "id": "ma_action",
            "priority": 10,
            "when": Equals(predicate="ma_presence", value="present"),
            "action": ClinicalAction(values={"decision": "refer"}),
        }
    )
    changed_guideline = guideline.model_copy(
        update={
            "id": "ma_only",
            "rules": [rule],
            "default_action": ClinicalAction(values={"decision": "routine"}),
        }
    )
    operator_map = minimal_problem.catalogue.operator_map()
    prerequisite = operator_map["quality_label"].model_copy(update={"cost": Decimal("2.0")})
    label = operator_map["ma_presence_label"].model_copy(
        update={
            "cost": Decimal("0.1"),
            "required_operator_ids": ["quality_label"],
            "required_evidence_conditions": [],
        }
    )
    catalogue = minimal_problem.catalogue.model_copy(update={"operators": [prerequisite, label]})
    return replace(
        minimal_problem,
        guidelines=(changed_guideline,),
        catalogue=catalogue,
        config=minimal_problem.config.model_copy(update={"required_operators": []}),
    )


def test_greedy_selects_and_pays_direct_prerequisite(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    problem = _ma_only_problem(minimal_problem)
    solution = compile_problem(problem, SolverKind.GREEDY)

    assert solution.selected_operators == ["ma_presence_label", "quality_label"]
    assert solution.total_cost == Decimal("2.1")


def test_finite_conflict_validation_ignores_infeasible_overlap(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
                {
                    "kind": "mutual_exclusion",
                    "conditions": [
                        {"predicate": "ma_presence", "equals": "present"},
                        {"predicate": "nv_presence", "equals": "present"},
                    ],
                }
            ],
        }
    )
    ontology = minimal_problem.ontology.model_copy(update={"feasibility": program})
    guideline = minimal_problem.guidelines[0]
    first = guideline.rules[0].model_copy(
        update={
            "id": "ma_action",
            "priority": 10,
            "when": Equals(predicate="ma_presence", value="present"),
            "action": ClinicalAction(values={"decision": "a"}),
        }
    )
    second = guideline.rules[1].model_copy(
        update={
            "id": "nv_action",
            "priority": 10,
            "when": Equals(predicate="nv_presence", value="present"),
            "action": ClinicalAction(values={"decision": "b"}),
        }
    )
    bundle = minimal_problem.guideline_bundles[0].model_copy(
        update={"guidelines": [guideline.model_copy(update={"rules": [first, second]})]}
    )

    validate_guidelines(bundle, ontology, conflict_state_limit=10_000)

    unconstrained = ontology.model_copy(update={"feasibility": FeasibilityProgram()})
    with pytest.raises(GuidelineValidationError, match="conflicting clauses"):
        validate_guidelines(bundle, unconstrained, conflict_state_limit=10_000)


@pytest.mark.parametrize("solver", list(SolverKind))
def test_empty_evidence_language_is_never_executable(minimal_problem, solver: SolverKind) -> None:  # type: ignore[no-untyped-def]
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
                {
                    "kind": "implication",
                    "if": {"predicate": "gradable", "equals": "yes"},
                    "then": {"predicate": "gradable", "equals": "no"},
                },
                {
                    "kind": "implication",
                    "if": {"predicate": "gradable", "equals": "no"},
                    "then": {"predicate": "gradable", "equals": "yes"},
                },
            ],
        }
    )
    ontology = minimal_problem.ontology.model_copy(update={"feasibility": program})
    problem = replace(minimal_problem, ontology=ontology)

    solution = compile_problem(problem, solver)

    assert solution.status.value == "UNSAT_EVIDENCE_LANGUAGE"
    with pytest.raises(CompilationError, match="UNSAT_EVIDENCE_LANGUAGE"):
        build_finite_problem(problem)
    with pytest.raises(CompilationError, match="cannot be certified"):
        build_certificate(problem, solution)


def test_partial_evaluation_applies_deterministic_derivation(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    graph = DerivationGraph(
        schema_version="1.1",
        graph_id="partial_derivation",
        version="1.1.0-synthetic",
        provenance=minimal_problem.graph.provenance,
        rules=[
            DerivationRule(
                id="ma_to_nv",
                input_predicates=["ma_presence"],
                output_predicates=["nv_presence"],
                value_mapping={"str:absent": "absent", "str:present": "present"},
                provenance=minimal_problem.graph.provenance,
            )
        ],
    )
    guideline = minimal_problem.guidelines[1].model_copy(
        update={"rules": [minimal_problem.guidelines[1].rules[1]]}
    )

    result = evaluate_guideline(
        guideline,
        EvidenceState(values={"ma_presence": "present"}),
        minimal_problem.ontology,
        derivations=graph,
    )

    assert [item.values["decision"] for item in result.actions] == ["urgent"]


def test_smt_conflict_validation_applies_derivations(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    provenance = minimal_problem.guidelines[0].rules[0].provenance
    first = (
        minimal_problem.guidelines[0]
        .rules[0]
        .model_copy(
            update={
                "id": "ma_present",
                "priority": 10,
                "when": Equals(predicate="ma_presence", value="present"),
                "action": ClinicalAction(values={"decision": "first"}),
                "provenance": provenance,
            }
        )
    )
    second = first.model_copy(
        update={
            "id": "nv_absent",
            "when": Equals(predicate="nv_presence", value="absent"),
            "action": ClinicalAction(values={"decision": "second"}),
        }
    )
    guideline = minimal_problem.guidelines[0].model_copy(
        update={"rules": [first, second], "default_action": None}
    )
    bundle = minimal_problem.guideline_bundles[0].model_copy(update={"guidelines": [guideline]})
    graph = DerivationGraph(
        schema_version="1.1",
        graph_id="conflict_derivation",
        version="1.1.0-synthetic",
        provenance=minimal_problem.graph.provenance,
        rules=[
            DerivationRule(
                id="ma_to_nv_conflict",
                input_predicates=["ma_presence"],
                output_predicates=["nv_presence"],
                value_mapping={"str:absent": "absent", "str:present": "present"},
                provenance=minimal_problem.graph.provenance,
            )
        ],
    )

    with pytest.raises(GuidelineValidationError, match="conflict"):
        validate_guidelines(bundle, minimal_problem.ontology, conflict_state_limit=1)
    validate_guidelines(
        bundle,
        minimal_problem.ontology,
        graph,
        conflict_state_limit=1,
    )


def test_identity_derived_equality_requires_typed_domain_compatibility(
    minimal_problem: Any,
) -> None:
    source = minimal_problem.ontology.predicates[0].model_copy(
        update={"id": "source", "value_type": "BOOLEAN", "allowed_values": [False, True]}
    )
    target = minimal_problem.ontology.predicates[0].model_copy(
        update={"id": "target", "value_type": "INTEGER", "allowed_values": [0, 1]}
    )
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
                {
                    "kind": "derived_equality",
                    "source_predicate": "source",
                    "target_predicate": "target",
                }
            ],
        }
    )
    ontology = minimal_problem.ontology.model_copy(
        update={"predicates": [source, target], "feasibility": program}
    )

    with pytest.raises(OntologyValidationError, match="identity"):
        validate_ontology(ontology)


def test_relevant_state_projection_preserves_exact_optimum(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    noise = minimal_problem.ontology.predicates[0].model_copy(
        update={
            "id": "unrelated_noise",
            "name": "Unrelated synthetic noise",
            "description": "Not referenced by any decision or constraint.",
            "requires": [],
            "recommended_operators": [],
        }
    )
    ontology = minimal_problem.ontology.model_copy(
        update={"predicates": [*minimal_problem.ontology.predicates, noise]}
    )
    noise_operator = minimal_problem.catalogue.operators[0].model_copy(
        update={
            "id": "unrelated_noise_label",
            "name": "Unrelated noise label",
            "output_predicates": ["unrelated_noise"],
            "required_operator_ids": [],
            "required_evidence_conditions": [],
        }
    )
    catalogue = minimal_problem.catalogue.model_copy(
        update={"operators": [*minimal_problem.catalogue.operators, noise_operator]}
    )
    problem = replace(minimal_problem, ontology=ontology, catalogue=catalogue)

    assert "unrelated_noise" not in relevant_predicate_closure(problem)
    assert len(enumerate_states(problem)) == 2 * len(enumerate_relevant_states(problem))
    full = solve_exact(build_finite_problem(problem))
    reduced = solve_exact(build_finite_problem(problem, relevant_only=True))
    assert (reduced.selected_operators, reduced.total_cost) == (
        full.selected_operators,
        full.total_cost,
    )


def test_relevant_projection_fails_closed_above_limit(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    problem = replace(
        minimal_problem,
        config=minimal_problem.config.model_copy(update={"max_states": 1}),
    )

    with pytest.raises(CompilationError, match="relevant finite state space"):
        enumerate_relevant_states(problem)


@pytest.mark.parametrize("seed", [0, 3])
def test_generated_feasibility_hash_regression(seed: int, tmp_path: Path) -> None:
    problem = load_compiler_problem(REGRESSION_ROOT / f"seed_{seed:04d}" / "project.yaml")
    solution = compile_problem(problem, SolverKind.EXACT)
    path = write_certificate(
        build_certificate(problem, solution), tmp_path / f"seed_{seed:04d}.json"
    )

    assert verify_certificate(path).valid


def test_compiler_constraint_dependency_extraction_covers_every_kind() -> None:
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
                {
                    "kind": "implication",
                    "if": {"predicate": "p0", "equals": True},
                    "then": {"predicate": "p1", "equals": True},
                },
                {
                    "kind": "mutual_exclusion",
                    "conditions": [
                        {"predicate": "p1", "equals": True},
                        {"predicate": "p2", "equals": True},
                    ],
                },
                {
                    "kind": "exactly_one",
                    "conditions": [
                        {"predicate": "p2", "equals": True},
                        {"predicate": "p3", "equals": True},
                    ],
                },
                {
                    "kind": "at_most_one",
                    "conditions": [
                        {"predicate": "p3", "equals": True},
                        {"predicate": "p4", "equals": True},
                    ],
                },
                {
                    "kind": "conditional_allowed",
                    "if": {"predicate": "p4", "equals": True},
                    "predicate": "p5",
                    "allowed_values": [True],
                },
                {
                    "kind": "derived_equality",
                    "source_predicate": "p5",
                    "target_predicate": "p6",
                },
                {
                    "kind": "parent_child",
                    "parent_predicate": "p6",
                    "child_predicate": "p7",
                    "when_parent_values": [True],
                    "allowed_child_values": [True],
                },
            ],
        }
    )

    extracted = [_constraint_predicates(item) for item in program.constraints]

    assert extracted == [
        {"p0", "p1"},
        {"p1", "p2"},
        {"p2", "p3"},
        {"p3", "p4"},
        {"p4", "p5"},
        {"p5", "p6"},
        {"p6", "p7"},
    ]


def test_independent_relevant_closure_traverses_all_dependencies() -> None:
    constraints = [
        {
            "kind": "implication",
            "if": {"predicate": "p0", "equals": True},
            "then": {"predicate": "p1", "equals": True},
        },
        {
            "kind": "mutual_exclusion",
            "conditions": [
                {"predicate": "p1", "equals": True},
                {"predicate": "p2", "equals": True},
            ],
        },
        {
            "kind": "exactly_one",
            "conditions": [
                {"predicate": "p2", "equals": True},
                {"predicate": "p3", "equals": True},
            ],
        },
        {
            "kind": "at_most_one",
            "conditions": [
                {"predicate": "p3", "equals": True},
                {"predicate": "p4", "equals": True},
            ],
        },
        {
            "kind": "conditional_allowed",
            "if": {"predicate": "p4", "equals": True},
            "predicate": "p5",
            "allowed_values": [True],
        },
        {
            "kind": "derived_equality",
            "source_predicate": "p5",
            "target_predicate": "p6",
        },
        {
            "kind": "parent_child",
            "parent_predicate": "p6",
            "child_predicate": "p7",
            "when_parent_values": [True],
            "allowed_child_values": [True],
        },
    ]
    ontology = {
        "predicates": [{"id": f"p{index}", "allowed_values": [False, True]} for index in range(10)],
        "feasibility": {"constraints": constraints},
    }
    guidelines = [
        {"rules": [{"when": {"eq": ["p0", True]}}]},
    ]
    operators = {
        "operators": [
            {
                "id": "observe_p8",
                "output_predicates": ["p7"],
                "required_operator_ids": ["prerequisite"],
                "required_evidence_conditions": [{"predicate_id": "p8"}],
            },
            {
                "id": "prerequisite",
                "output_predicates": ["p9"],
                "required_operator_ids": [],
                "required_evidence_conditions": [],
            },
        ]
    }
    graph = {
        "rules": [
            {"input_predicates": ["p7"], "output_predicates": ["p8"]},
        ]
    }

    assert _relevant_predicates(ontology, guidelines, operators, graph) == [
        f"p{index}" for index in range(10)
    ]


def test_defensive_dependency_and_portable_path_boundaries(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        _constraint_predicates(object())
    with pytest.raises(CertificateVerificationError, match="unsupported feasibility"):
        verifier_constraint_predicates({"kind": "unsupported"})

    root = tmp_path / "root"
    outside = tmp_path / "outside" / "source.yaml"
    assert _portable(outside, root) == outside.resolve().as_posix()
    assert _repository_root(Path("/proc/g2lc-no-marker/source.yaml")) == Path.cwd().resolve()
