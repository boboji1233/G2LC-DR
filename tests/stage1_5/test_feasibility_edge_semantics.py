from __future__ import annotations

from typing import Any

import z3

from g2lc.compiler.problem import LoadedCompilerProblem
from g2lc.ontology.feasibility import (
    condition_value,
    feasibility_constraints_z3,
    feasible_completions,
    is_feasible_state,
)
from g2lc.ontology.models import EvidenceCondition, EvidenceOntology, FeasibilityProgram
from g2lc.types import EvidenceState, scalar_key


def _ontology(
    minimal_problem: LoadedCompilerProblem, constraints: list[dict[str, Any]]
) -> EvidenceOntology:
    program = FeasibilityProgram.model_validate(
        {"schema_version": "1.0", "constraints": constraints}
    )
    return minimal_problem.ontology.model_copy(update={"feasibility": program})


def test_partial_condition_and_implication_edges(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    condition = EvidenceCondition(predicate="gradable", equals="yes")
    assert condition_value(condition, EvidenceState(values={})) is None
    assert condition_value(condition, EvidenceState(values={"gradable": "yes"})) is True
    assert condition_value(condition, EvidenceState(values={"gradable": "no"})) is False
    ontology = _ontology(
        minimal_problem,
        [
            {
                "kind": "implication",
                "if": {"predicate": "gradable", "equals": "yes"},
                "then": {"predicate": "ma_presence", "equals": "present"},
            }
        ],
    )
    assert not is_feasible_state(
        EvidenceState(values={"gradable": "yes", "ma_presence": "absent"}),
        ontology,
        complete=False,
    )
    assert not is_feasible_state(EvidenceState(values={"gradable": "yes"}), ontology, complete=True)


def test_conditional_cardinality_and_missing_value_edges(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    conditional = _ontology(
        minimal_problem,
        [
            {
                "kind": "conditional_allowed",
                "if": {"predicate": "gradable", "equals": "yes"},
                "predicate": "ma_presence",
                "allowed_values": ["present"],
            }
        ],
    )
    assert not is_feasible_state(
        EvidenceState(values={"gradable": "yes", "ma_presence": "absent"}),
        conditional,
        complete=False,
    )
    assert not is_feasible_state(
        EvidenceState(values={"gradable": "yes"}), conditional, complete=True
    )

    exactly_one = _ontology(
        minimal_problem,
        [
            {
                "kind": "exactly_one",
                "conditions": [
                    {"predicate": "ma_presence", "equals": "present"},
                    {"predicate": "nv_presence", "equals": "present"},
                ],
            }
        ],
    )
    assert not is_feasible_state(
        EvidenceState(values={"ma_presence": "present", "nv_presence": "present"}),
        exactly_one,
        complete=False,
    )
    assert not is_feasible_state(
        EvidenceState(values={"ma_presence": "absent", "nv_presence": "absent"}),
        exactly_one,
        complete=True,
    )
    assert not is_feasible_state(
        EvidenceState(values={"ma_presence": "absent", "nv_presence": "absent"}),
        exactly_one,
        complete=False,
    )


def test_derived_equality_and_parent_child_missing_edges(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    derived = _ontology(
        minimal_problem,
        [
            {
                "kind": "derived_equality",
                "source_predicate": "ma_presence",
                "target_predicate": "nv_presence",
                "value_mapping": {
                    "str:absent": "absent",
                    "str:present": "present",
                },
            }
        ],
    )
    assert is_feasible_state(EvidenceState(values={}), derived, complete=False)
    assert not is_feasible_state(EvidenceState(values={}), derived, complete=True)
    assert not is_feasible_state(
        EvidenceState(values={"ma_presence": "present", "nv_presence": "absent"}),
        derived,
        complete=True,
    )

    parent = _ontology(
        minimal_problem,
        [
            {
                "kind": "parent_child",
                "parent_predicate": "gradable",
                "child_predicate": "hem_count_bin",
                "when_parent_values": ["no"],
                "allowed_child_values": ["0"],
            }
        ],
    )
    assert is_feasible_state(EvidenceState(values={}), parent, complete=False)
    assert not is_feasible_state(EvidenceState(values={}), parent, complete=True)
    assert not is_feasible_state(
        EvidenceState(values={"gradable": "no", "hem_count_bin": "4_plus"}),
        parent,
        complete=True,
    )


def test_feasible_completion_and_generic_z3_translation(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    constraints: list[dict[str, Any]] = [
        {
            "kind": "implication",
            "if": {"predicate": "gradable", "equals": "no"},
            "then": {"predicate": "ma_presence", "equals": "absent"},
        },
        {
            "kind": "mutual_exclusion",
            "conditions": [
                {"predicate": "ma_presence", "equals": "present"},
                {"predicate": "nv_presence", "equals": "present"},
            ],
        },
        {
            "kind": "conditional_allowed",
            "if": {"predicate": "gradable", "equals": "no"},
            "predicate": "hem_count_bin",
            "allowed_values": ["0"],
        },
        {
            "kind": "exactly_one",
            "conditions": [
                {"predicate": "ma_presence", "equals": "absent"},
                {"predicate": "ma_presence", "equals": "present"},
            ],
        },
        {
            "kind": "at_most_one",
            "conditions": [
                {"predicate": "ma_presence", "equals": "present"},
                {"predicate": "nv_presence", "equals": "present"},
            ],
        },
        {
            "kind": "derived_equality",
            "source_predicate": "ma_presence",
            "target_predicate": "nv_presence",
            "value_mapping": {
                "str:absent": "absent",
                "str:present": "present",
            },
        },
        {
            "kind": "parent_child",
            "parent_predicate": "gradable",
            "child_predicate": "hem_count_bin",
            "when_parent_values": ["no"],
            "allowed_child_values": ["0"],
        },
    ]
    ontology = _ontology(minimal_problem, constraints)
    completions = list(feasible_completions(EvidenceState(values={"gradable": "no"}), ontology))
    assert completions
    assert all(item.value("hem_count_bin") == "0" for item in completions)

    variables = {item.id: z3.Int(f"generic__{item.id}") for item in ontology.predicates}
    indices = {
        item.id: {scalar_key(value): index for index, value in enumerate(item.allowed_values)}
        for item in ontology.predicates
    }
    translated = feasibility_constraints_z3(ontology, variables, indices)
    assert len(translated) == len(constraints)
    assert all(z3.is_bool(item) for item in translated)
