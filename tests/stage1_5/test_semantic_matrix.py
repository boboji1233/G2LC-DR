from __future__ import annotations

import itertools
import random
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
import z3
from ortools.sat.python import cp_model

from g2lc.compiler.api import compile_problem
from g2lc.compiler.counterexample import (
    _domain_index,
    _feasibility_constraints_z3,
    find_counterexample,
    solve_counterexample_separation,
)
from g2lc.compiler.exact import brute_force_optimum, solve_exact, solve_lexicographic_model
from g2lc.compiler.problem import LoadedCompilerProblem, build_finite_problem, enumerate_states
from g2lc.compiler.result import CompilerStatus, SolverKind, SolverStatus
from g2lc.errors import GuidelineValidationError, OperatorValidationError
from g2lc.guidelines.ast import And, ClinicalAction, Equals, Expression, Known
from g2lc.guidelines.validator import validate_guidelines
from g2lc.ontology.feasibility import feasibility_predicates, is_feasible_state
from g2lc.ontology.models import FeasibilityProgram
from g2lc.ontology.validator import validate_ontology
from g2lc.operators.derivation import observation_signature
from g2lc.operators.lattice import validate_operators
from g2lc.operators.models import (
    DerivationGraph,
    DerivationRule,
    OperatorAvailability,
)
from g2lc.types import EvidenceState, Modality, scalar_key


def _feasible_problem(minimal_problem: LoadedCompilerProblem) -> LoadedCompilerProblem:
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
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
            ],
        }
    )
    ontology = minimal_problem.ontology.model_copy(update={"feasibility": program})
    validate_ontology(ontology)
    return replace(minimal_problem, ontology=ontology)


def test_feasibility_python_and_z3_enumerate_identical_states(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    problem = _feasible_problem(minimal_problem)
    python_states = enumerate_states(problem)
    assert python_states
    assert all(is_feasible_state(item, problem.ontology, complete=True) for item in python_states)

    variables = {item.id: z3.Int(f"state__{item.id}") for item in problem.ontology.predicates}
    indices = _domain_index(problem)
    solver = z3.Solver()
    for predicate in problem.ontology.predicates:
        solver.add(variables[predicate.id] >= 0)
        solver.add(variables[predicate.id] < len(predicate.allowed_values))
    solver.add(*_feasibility_constraints_z3(variables, problem, indices))
    z3_states: set[tuple[str, ...]] = set()
    ordered = sorted(problem.ontology.predicates, key=lambda item: item.id)
    while solver.check() == z3.sat:
        model = solver.model()
        indices_row = [model.eval(variables[item.id]).as_long() for item in ordered]
        z3_states.add(
            tuple(
                scalar_key(item.allowed_values[index])
                for item, index in zip(ordered, indices_row, strict=True)
            )
        )
        solver.add(
            z3.Or(
                *[
                    variables[item.id] != index
                    for item, index in zip(ordered, indices_row, strict=True)
                ]
            )
        )
    python_rows = {
        tuple(scalar_key(state.values[item.id]) for item in ordered) for state in python_states
    }
    assert z3_states == python_rows
    assert feasibility_predicates(problem.ontology) == {
        "gradable",
        "hem_count_bin",
        "ma_presence",
        "nv_presence",
    }


def test_infeasible_state_cannot_form_a_false_counterexample(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    problem = _feasible_problem(minimal_problem)
    infeasible = EvidenceState(
        values={
            "gradable": "no",
            "ma_presence": "present",
            "hem_count_bin": "0",
            "nv_presence": "absent",
        }
    )
    assert not is_feasible_state(infeasible, problem.ontology, complete=True)
    assert infeasible not in enumerate_states(problem)


def test_unary_derivation_is_total_computed_and_filters_states(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    graph = DerivationGraph(
        schema_version="1.1",
        graph_id="deterministic_unary",
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
    validate_operators(minimal_problem.catalogue, graph, minimal_problem.ontology)
    problem = replace(minimal_problem, graph=graph)
    assert len(enumerate_states(problem)) == 12

    operator = minimal_problem.catalogue.operator_map()["ma_presence_label"]
    left = EvidenceState(
        values={"gradable": "yes", "ma_presence": "present", "nv_presence": "absent"}
    )
    right = EvidenceState(
        values={"gradable": "yes", "ma_presence": "present", "nv_presence": "present"}
    )
    assert observation_signature([operator], graph, left) == observation_signature(
        [operator], graph, right
    )


def test_incomplete_unary_derivation_table_is_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    graph = DerivationGraph(
        schema_version="1.1",
        graph_id="incomplete_table",
        version="1.1.0-synthetic",
        provenance=minimal_problem.graph.provenance,
        rules=[
            DerivationRule(
                id="ma_to_nv",
                input_predicates=["ma_presence"],
                output_predicates=["nv_presence"],
                value_mapping={"str:absent": "absent"},
                provenance=minimal_problem.graph.provenance,
            )
        ],
    )
    with pytest.raises(OperatorValidationError, match="total"):
        validate_operators(minimal_problem.catalogue, graph, minimal_problem.ontology)


def test_large_guideline_bundle_uses_smt_instead_of_skipping_validation(
    minimal_problem: Any,
) -> None:
    template = minimal_problem.ontology.predicates[0]
    predicates = [
        template.model_copy(
            update={
                "id": f"p{index}",
                "requires": [],
                "recommended_operators": [],
            }
        )
        for index in range(14)
    ]
    ontology = minimal_problem.ontology.model_copy(update={"predicates": predicates})
    terms: list[Expression] = [Known(predicate=f"p{index}") for index in range(14)]
    terms.append(Equals(predicate="p0", value="yes"))
    guideline = minimal_problem.guidelines[0]
    first = guideline.rules[0].model_copy(
        update={
            "id": "large_first",
            "priority": 10,
            "when": And(terms=terms),
            "action": ClinicalAction(values={"decision": "first"}),
        }
    )
    second = guideline.rules[1].model_copy(
        update={
            "id": "large_second",
            "priority": 10,
            "when": And(terms=terms),
            "action": ClinicalAction(values={"decision": "second"}),
        }
    )
    changed = guideline.model_copy(update={"rules": [first, second]})
    bundle = minimal_problem.guideline_bundles[0].model_copy(update={"guidelines": [changed]})
    with pytest.raises(GuidelineValidationError, match="SMT witness"):
        validate_guidelines(bundle, ontology, conflict_state_limit=10_000)


def test_operator_prerequisite_cycle_is_rejected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    base = minimal_problem.catalogue.operator_map()["image_level_grade"]
    first = base.model_copy(update={"id": "first", "required_operator_ids": ["second"]})
    second = base.model_copy(update={"id": "second", "required_operator_ids": ["first"]})
    catalogue = minimal_problem.catalogue.model_copy(update={"operators": [first, second]})
    with pytest.raises(OperatorValidationError, match="cyclic operator prerequisite"):
        validate_operators(catalogue, minimal_problem.graph, minimal_problem.ontology)


def test_operator_prerequisite_chain_is_selected_and_costed(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    solution = compile_problem(minimal_problem, SolverKind.EXACT)
    operator_map = minimal_problem.catalogue.operator_map()
    selected = set(solution.selected_operators)
    assert solution.status is CompilerStatus.EXECUTABLE
    assert "quality_label" in selected
    assert all(
        set(operator_map[item].required_operator_ids).issubset(selected) for item in selected
    )
    assert solution.total_cost == Decimal("5.00")


def test_required_modality_excludes_operator_from_cfp_project(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    base = minimal_problem.catalogue.operator_map()["image_level_grade"]
    oct_required = base.model_copy(
        update={
            "id": "oct_required",
            "modalities": [Modality.CFP, Modality.OCT],
            "required_modalities": [Modality.OCT],
        }
    )
    catalogue = minimal_problem.catalogue.model_copy(update={"operators": [oct_required]})
    problem = replace(minimal_problem, catalogue=catalogue)
    assert problem.available_operators() == []


def test_sub_milliscale_costs_are_not_rounded_before_optimization(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    operators = []
    quality = minimal_problem.catalogue.operator_map()["quality_label"]
    for operator in minimal_problem.catalogue.operators:
        operators.append(
            operator.model_copy(
                update={
                    "cost": Decimal("0.00049") if operator.id == "quality_label" else operator.cost,
                    "required_operator_ids": [],
                    "required_evidence_conditions": [],
                }
            )
        )
    operators.append(
        quality.model_copy(update={"id": "z_quality_cheaper", "cost": Decimal("0.0004")})
    )
    catalogue = minimal_problem.catalogue.model_copy(update={"operators": operators})
    problem = replace(minimal_problem, catalogue=catalogue)
    finite = build_finite_problem(problem)
    exact = solve_exact(finite)
    brute = brute_force_optimum(finite)
    assert brute is not None
    assert exact.selected_operators == brute[0]
    assert exact.total_cost == brute[1]
    assert "z_quality_cheaper" in exact.selected_operators
    assert "quality_label" not in exact.selected_operators


def test_incremental_repair_does_not_replace_available_base(missing_problem) -> None:  # type: ignore[no-untyped-def]
    quality = missing_problem.catalogue.operator_map()["quality_label"]
    expensive_quality = quality.model_copy(update={"cost": Decimal("100")})
    cheap_replacement = quality.model_copy(
        update={
            "id": "cheap_quality_replacement",
            "cost": Decimal("0.1"),
            "availability": OperatorAvailability.UNAVAILABLE,
        }
    )
    operators = [
        expensive_quality if item.id == "quality_label" else item
        for item in missing_problem.catalogue.operators
    ]
    catalogue = missing_problem.catalogue.model_copy(
        update={"operators": [*operators, cheap_replacement]}
    )
    problem = replace(missing_problem, catalogue=catalogue)
    solution = compile_problem(problem, SolverKind.EXACT)
    assert solution.status is CompilerStatus.INCOMPLETE
    assert solution.minimal_additions == ["nv_presence_label"]
    assert solution.minimum_repair_cost == Decimal("1.5")


def test_unavailable_prerequisite_is_included_in_incremental_repair(missing_problem) -> None:  # type: ignore[no-untyped-def]
    operator_map = missing_problem.catalogue.operator_map()
    repair_gate = operator_map["quality_label"].model_copy(
        update={
            "id": "repair_gate",
            "availability": OperatorAvailability.UNAVAILABLE,
            "cost": Decimal("0.25"),
        }
    )
    nv_operator = operator_map["nv_presence_label"].model_copy(
        update={"required_operator_ids": ["quality_label", "repair_gate"]}
    )
    operators = [
        nv_operator if item.id == "nv_presence_label" else item
        for item in missing_problem.catalogue.operators
    ]
    catalogue = missing_problem.catalogue.model_copy(
        update={"operators": [*operators, repair_gate]}
    )
    problem = replace(missing_problem, catalogue=catalogue)

    solution = compile_problem(problem, SolverKind.EXACT)

    assert solution.minimal_additions == ["nv_presence_label", "repair_gate"]
    assert solution.minimum_repair_cost == Decimal("1.75")


def test_equal_cost_objective_uses_lexicographic_operator_id_tie_break() -> None:
    model = cp_model.CpModel()
    variables = {item: model.new_bool_var(item) for item in ("a", "b")}
    model.add(variables["a"] + variables["b"] >= 1)

    selected, status = solve_lexicographic_model(
        model,
        variables,
        {"a": Decimal("1.000"), "b": Decimal("1.000")},
        seed=0,
    )

    assert status is SolverStatus.OPTIMAL
    assert selected == ["a"]


@pytest.mark.parametrize("seed", range(5))
def test_seeded_small_solver_equivalence(minimal_problem, seed: int) -> None:  # type: ignore[no-untyped-def]
    randomizer = random.Random(seed)
    operators = [
        item.model_copy(update={"cost": Decimal(randomizer.randint(1, 5000)) / Decimal("1000000")})
        for item in minimal_problem.catalogue.operators
    ]
    catalogue = minimal_problem.catalogue.model_copy(update={"operators": operators})
    problem = replace(minimal_problem, catalogue=catalogue)
    finite = build_finite_problem(problem)
    exact = solve_exact(finite)
    brute = brute_force_optimum(finite)
    separation = solve_counterexample_separation(problem)
    assert brute is not None
    assert exact.solver_status is SolverStatus.OPTIMAL
    assert (exact.selected_operators, exact.total_cost) == brute
    assert separation.solver_status is SolverStatus.OPTIMAL
    assert (separation.selected_operators, separation.total_cost) == brute
    assert find_counterexample(problem, separation.selected_operators) is None


def test_finite_and_z3_executability_agree_for_all_small_schemes(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    finite = build_finite_problem(minimal_problem)
    operator_ids = [item.id for item in finite.operators]
    universe = set(range(len(finite.pairs)))
    operator_map = {item.id: item for item in finite.operators}
    for flags in itertools.product((False, True), repeat=len(operator_ids)):
        selected = {item for item, enabled in zip(operator_ids, flags, strict=True) if enabled}
        if any(
            not set(operator_map[item].required_operator_ids).issubset(selected)
            for item in selected
        ):
            continue
        covered = set().union(*(finite.coverage[item] for item in selected)) if selected else set()
        assert (covered == universe) is (
            find_counterexample(minimal_problem, sorted(selected)) is None
        )
