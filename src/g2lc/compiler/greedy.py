"""Deterministic marginal separation-benefit per cost solver."""

from __future__ import annotations

from decimal import Decimal

from g2lc.compiler.dominance import dominated_operators
from g2lc.compiler.exact import _counterexample
from g2lc.compiler.problem import FiniteProblem
from g2lc.compiler.result import (
    CompilerSolution,
    CompilerStatus,
    SolverKind,
    SolverStatus,
)
from g2lc.operators.cost import scheme_cost, weighted_cost
from g2lc.operators.derivation import exact_observed_predicates


def solve_greedy(finite: FiniteProblem) -> CompilerSolution:
    """Greedily cover action-separating pairs with deterministic tie-breaking."""

    universe = set(range(len(finite.pairs)))
    selected_ids = set(finite.loaded.config.required_operators)
    operator_map = {operator.id: operator for operator in finite.operators}
    if not selected_ids.issubset(operator_map):
        missing = sorted(selected_ids - operator_map.keys())
        return CompilerSolution(
            status=CompilerStatus.INCOMPLETE,
            solver=SolverKind.GREEDY,
            solver_status=SolverStatus.INFEASIBLE,
            missing_predicates=missing,
            required_pair_count=len(universe),
        )
    covered = (
        set().union(*(finite.coverage[item] for item in selected_ids)) if selected_ids else set()
    )
    dominated = dominated_operators(finite)
    candidates = [
        operator
        for operator in finite.operators
        if operator.id not in selected_ids and operator.id not in dominated
    ]
    iterations = 0
    while covered != universe:
        remaining = universe - covered
        scored: list[tuple[Decimal, int, str]] = []
        for operator in candidates:
            benefit = len(finite.coverage[operator.id] & remaining)
            if benefit == 0:
                continue
            cost = weighted_cost(operator, finite.loaded.config.instability_weight)
            ratio = Decimal("Infinity") if cost == 0 else Decimal(benefit) / cost
            scored.append((ratio, benefit, operator.id))
        if not scored:
            unresolved = sorted(universe - covered)
            return CompilerSolution(
                status=CompilerStatus.INCOMPLETE,
                solver=SolverKind.GREEDY,
                solver_status=SolverStatus.INFEASIBLE,
                selected_operators=sorted(selected_ids),
                total_cost=scheme_cost(
                    [operator_map[item] for item in sorted(selected_ids)],
                    finite.loaded.config.instability_weight,
                ),
                separated_pair_count=len(covered),
                required_pair_count=len(universe),
                iterations=iterations,
                counterexamples=[_counterexample(finite, item) for item in unresolved[:10]],
            )
        _, _, chosen_id = min(scored, key=lambda item: (-item[0], -item[1], item[2]))
        selected_ids.add(chosen_id)
        covered.update(finite.coverage[chosen_id])
        candidates = [operator for operator in candidates if operator.id != chosen_id]
        iterations += 1
    selected = [operator_map[item] for item in sorted(selected_ids)]
    return CompilerSolution(
        status=CompilerStatus.EXECUTABLE,
        solver=SolverKind.GREEDY,
        solver_status=SolverStatus.FEASIBLE,
        selected_operators=sorted(selected_ids),
        derived_predicates=sorted(exact_observed_predicates(selected, finite.loaded.graph)),
        total_cost=scheme_cost(selected, finite.loaded.config.instability_weight),
        optimal=False,
        separated_pair_count=len(covered),
        required_pair_count=len(universe),
        iterations=iterations,
    )
