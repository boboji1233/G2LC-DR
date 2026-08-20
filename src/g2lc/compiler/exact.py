"""CP-SAT and brute-force solvers for finite weighted test cover."""

from __future__ import annotations

import itertools
from decimal import ROUND_HALF_UP, Decimal

from ortools.sat.python import cp_model

from g2lc.compiler.problem import FiniteProblem, make_counterexample
from g2lc.compiler.result import (
    CompilerSolution,
    CompilerStatus,
    Counterexample,
    SolverKind,
    SolverStatus,
)
from g2lc.errors import CompilationError
from g2lc.operators.cost import scheme_cost, weighted_cost
from g2lc.operators.derivation import exact_observed_predicates


def _units(value: float) -> int:
    return int((Decimal(str(value)) * Decimal("1000")).quantize(Decimal("1"), ROUND_HALF_UP))


def _counterexample(finite: FiniteProblem, pair_index: int) -> Counterexample:
    left, right, pair = make_counterexample(finite, pair_index)
    return Counterexample(
        left=left,
        right=right,
        differing_guidelines=list(pair.differing_guidelines),
        left_actions={
            key: finite.action_signatures[pair.left_index][key] for key in pair.differing_guidelines
        },
        right_actions={
            key: finite.action_signatures[pair.right_index][key]
            for key in pair.differing_guidelines
        },
    )


def solve_exact(finite: FiniteProblem) -> CompilerSolution:
    """Solve every explicit separation constraint with deterministic CP-SAT settings."""

    operators = list(finite.operators)
    operator_map = {operator.id: operator for operator in operators}
    required = set(finite.loaded.config.required_operators)
    unavailable_required = sorted(required - operator_map.keys())
    if unavailable_required:
        raise CompilationError(
            f"required operators are not available in this project: {unavailable_required}"
        )
    uncovered = [
        pair_index
        for pair_index in range(len(finite.pairs))
        if not any(pair_index in finite.coverage[operator.id] for operator in operators)
    ]
    if uncovered:
        return CompilerSolution(
            status=CompilerStatus.INCOMPLETE,
            solver=SolverKind.EXACT,
            solver_status=SolverStatus.INFEASIBLE,
            required_pair_count=len(finite.pairs),
            separated_pair_count=len(finite.pairs) - len(uncovered),
            counterexamples=[_counterexample(finite, item) for item in uncovered[:10]],
        )

    model = cp_model.CpModel()
    variables = {operator.id: model.new_bool_var(operator.id) for operator in operators}
    for pair_index in range(len(finite.pairs)):
        separating = [
            variables[operator.id]
            for operator in operators
            if pair_index in finite.coverage[operator.id]
        ]
        model.add(sum(separating) >= 1)
    for operator_id in sorted(required):
        model.add(variables[operator_id] == 1)

    count_factor = len(operators) + 1
    coefficients = {
        operator.id: _units(weighted_cost(operator, finite.loaded.config.instability_weight))
        * count_factor
        + 1
        for operator in operators
    }
    model.minimize(sum(coefficients[item] * variables[item] for item in sorted(variables)))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = finite.loaded.config.seed
    status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        raise CompilationError(f"CP-SAT failed with status {solver.status_name(status)}")
    selected = [operator for operator in operators if solver.value(variables[operator.id])]
    selected.sort(key=lambda item: item.id)
    separated = set().union(*(finite.coverage[item.id] for item in selected)) if selected else set()
    return CompilerSolution(
        status=CompilerStatus.EXECUTABLE,
        solver=SolverKind.EXACT,
        solver_status=SolverStatus.OPTIMAL if status == cp_model.OPTIMAL else SolverStatus.FEASIBLE,
        selected_operators=[item.id for item in selected],
        derived_predicates=sorted(exact_observed_predicates(selected, finite.loaded.graph)),
        total_cost=scheme_cost(selected, finite.loaded.config.instability_weight),
        optimal=status == cp_model.OPTIMAL,
        separated_pair_count=len(separated),
        required_pair_count=len(finite.pairs),
        iterations=1,
    )


def brute_force_optimum(
    finite: FiniteProblem,
    *,
    max_operators: int = 24,
) -> tuple[list[str], float] | None:
    """Independently enumerate all small schemes and return a deterministic optimum."""

    operators = list(finite.operators)
    if len(operators) > max_operators:
        raise CompilationError(
            f"brute-force verification limited to {max_operators} operators, got {len(operators)}"
        )
    universe = set(range(len(finite.pairs)))
    required = set(finite.loaded.config.required_operators)
    best_key: tuple[float, int, tuple[str, ...]] | None = None
    best_ids: list[str] | None = None
    for flags in itertools.product((False, True), repeat=len(operators)):
        selected = [operator for operator, flag in zip(operators, flags, strict=True) if flag]
        ids = tuple(sorted(operator.id for operator in selected))
        if not required.issubset(ids):
            continue
        covered = (
            set().union(*(finite.coverage[item.id] for item in selected)) if selected else set()
        )
        if covered != universe:
            continue
        cost = scheme_cost(selected, finite.loaded.config.instability_weight)
        key = (cost, len(selected), ids)
        if best_key is None or key < best_key:
            best_key = key
            best_ids = list(ids)
    if best_key is None or best_ids is None:
        return None
    return best_ids, best_key[0]
