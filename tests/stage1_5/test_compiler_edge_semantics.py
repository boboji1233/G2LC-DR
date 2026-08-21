from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
import z3
from ortools.sat.python import cp_model
from pydantic import ValidationError

from g2lc.compiler.api import compile_problem
from g2lc.compiler.counterexample import (
    _derivation_constraints_z3,
    _domain_index,
    _expression_to_z3,
    _guideline_action_z3,
    solve_counterexample_separation,
)
from g2lc.compiler.exact import (
    _cost_scale,
    brute_force_optimum,
    solve_exact,
    solve_lexicographic_model,
)
from g2lc.compiler.greedy import solve_greedy
from g2lc.compiler.problem import (
    CompilerProblem,
    build_finite_problem,
    enumerate_states,
)
from g2lc.compiler.result import CompilerStatus, SolverKind, SolverStatus
from g2lc.errors import CompilationError
from g2lc.guidelines.ast import (
    And,
    Equals,
    Expression,
    GreaterEqual,
    InSet,
    Known,
    LessEqual,
    Not,
)
from g2lc.operators.models import DerivationGraph, DerivationRule


def test_symbolic_expression_and_derivation_cover_full_contract(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    problem = minimal_problem
    variables = {item.id: z3.Int(f"v__{item.id}") for item in problem.ontology.predicates}
    indices = _domain_index(problem)
    expressions: list[Expression] = [
        And(terms=[Known(predicate="gradable"), Equals(predicate="gradable", value="yes")]),
        Not(term=Equals(predicate="gradable", value="no")),
        InSet(predicate="gradable", values=["yes"]),
    ]
    assert all(
        z3.is_bool(_expression_to_z3(item, variables, problem, indices)) for item in expressions
    )

    numeric = problem.ontology.predicates[0].model_copy(
        update={"value_type": "INTEGER", "allowed_values": [1, 2]}
    )
    numeric_problem = replace(
        problem,
        ontology=problem.ontology.model_copy(update={"predicates": [numeric]}),
        guidelines=(problem.guidelines[0],),
    )
    numeric_variables = {"gradable": z3.Int("numeric")}
    numeric_indices = {"gradable": {"int:1": 0, "int:2": 1}}
    assert z3.is_bool(
        _expression_to_z3(
            GreaterEqual(predicate="gradable", value=2),
            numeric_variables,
            numeric_problem,
            numeric_indices,
        )
    )
    assert z3.is_bool(
        _expression_to_z3(
            LessEqual(predicate="gradable", value=1),
            numeric_variables,
            numeric_problem,
            numeric_indices,
        )
    )

    graph = DerivationGraph(
        schema_version="1.1",
        graph_id="z3_derivation",
        version="1.1.0-synthetic",
        provenance=problem.graph.provenance,
        rules=[
            DerivationRule(
                id="ma_to_nv",
                input_predicates=["ma_presence"],
                output_predicates=["nv_presence"],
                value_mapping={"str:absent": "absent", "str:present": "present"},
                provenance=problem.graph.provenance,
            )
        ],
    )
    derived_problem = replace(problem, graph=graph)
    constraints = _derivation_constraints_z3(variables, derived_problem, indices)
    assert len(constraints) == 1
    assert z3.is_bool(constraints[0])

    action = _guideline_action_z3(problem.guidelines[0], variables, problem, indices)
    assert z3.is_arith(action)
    no_default = problem.guidelines[0].model_copy(update={"default_action": None})
    assert z3.is_arith(_guideline_action_z3(no_default, variables, problem, indices))


def test_exact_objective_defensive_status_and_limits(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CompilationError, match="finite decimals"):
        _cost_scale([Decimal("NaN")])

    model = cp_model.CpModel()
    variables = {f"op_{index}": model.new_bool_var(f"op_{index}") for index in range(61)}
    with pytest.raises(CompilationError, match="60 operators"):
        solve_lexicographic_model(
            model,
            variables,
            {item: Decimal(1) for item in variables},
            seed=0,
        )

    infeasible_model = cp_model.CpModel()
    variable = infeasible_model.new_bool_var("only")
    infeasible_model.add(variable == 0)
    infeasible_model.add(variable == 1)
    assert solve_lexicographic_model(
        infeasible_model, {"only": variable}, {"only": Decimal(1)}, seed=0
    ) == ([], SolverStatus.INFEASIBLE)

    finite = build_finite_problem(minimal_problem)
    operators = tuple(
        finite.operators[0].model_copy(update={"id": f"operator_{index}"}) for index in range(25)
    )
    oversized = replace(
        finite,
        operators=operators,
        coverage={item.id: frozenset() for item in operators},
    )
    with pytest.raises(CompilationError, match="24 operators"):
        brute_force_optimum(oversized)

    impossible = replace(
        finite,
        coverage={item.id: frozenset() for item in finite.operators},
    )
    assert brute_force_optimum(impossible) is None


def test_problem_validation_limits_constraints_and_oos(minimal_problem, oos_problem) -> None:  # type: ignore[no-untyped-def]
    raw = minimal_problem.config.model_dump()
    raw["required_operators"] = ["x", "x"]
    with pytest.raises(ValidationError, match="unique"):
        CompilerProblem.model_validate(raw)

    tiny = replace(
        minimal_problem,
        config=minimal_problem.config.model_copy(update={"max_states": 1}),
    )
    with pytest.raises(CompilationError, match="exceeding max_states"):
        enumerate_states(tiny)
    with pytest.raises(CompilationError, match="OOS"):
        build_finite_problem(oos_problem)

    required_missing = replace(
        minimal_problem,
        config=minimal_problem.config.model_copy(
            update={"required_operators": ["unknown_operator"]}
        ),
    )
    with pytest.raises(CompilationError, match="required operators"):
        solve_exact(build_finite_problem(required_missing))


def test_candidate_pruning_greedy_and_separation_failure_outcomes(
    minimal_problem: Any, missing_problem: Any
) -> None:
    base = minimal_problem.catalogue.operator_map()["image_level_grade"]
    blocked = base.model_copy(
        update={"id": "blocked", "required_operator_ids": ["not_in_catalogue"]}
    )
    pruned_problem = replace(
        minimal_problem,
        catalogue=minimal_problem.catalogue.model_copy(update={"operators": [blocked]}),
    )
    assert pruned_problem.available_operators() == []

    finite = build_finite_problem(minimal_problem)
    greedy_missing = replace(
        finite,
        loaded=replace(
            minimal_problem,
            config=minimal_problem.config.model_copy(
                update={"required_operators": ["not_available"]}
            ),
        ),
    )
    assert solve_greedy(greedy_missing).status is CompilerStatus.INCOMPLETE

    no_coverage = replace(
        finite,
        coverage={item.id: frozenset() for item in finite.operators},
    )
    assert solve_greedy(no_coverage).status is CompilerStatus.INCOMPLETE

    limited = solve_counterexample_separation(minimal_problem, max_iterations=0)
    assert limited.solver_status is SolverStatus.LIMIT_REACHED
    missing = compile_problem(missing_problem, SolverKind.SEPARATION)
    assert missing.status is CompilerStatus.INCOMPLETE
    assert missing.missing_predicates == ["nv_presence"]
