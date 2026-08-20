"""Deterministic marginal separation-benefit per cost solver."""

from __future__ import annotations

from decimal import Decimal

from g2lc.compiler.dominance import dominated_operators
from g2lc.compiler.exact import _counterexample
from g2lc.compiler.problem import FiniteProblem, scheme_coverage
from g2lc.compiler.result import (
    CompilerSolution,
    CompilerStatus,
    SolverKind,
    SolverStatus,
)
from g2lc.operators.cost import scheme_cost, weighted_cost
from g2lc.operators.derivation import exact_observed_predicates
from g2lc.operators.lattice import operator_prerequisite_closure


def solve_greedy(finite: FiniteProblem) -> CompilerSolution:
    """Greedily cover action-separating pairs with deterministic tie-breaking."""

    universe = set(range(len(finite.pairs)))
    operator_map = {operator.id: operator for operator in finite.operators}
    required_ids = set(finite.loaded.config.required_operators)
    if not required_ids.issubset(operator_map):
        missing = sorted(required_ids - operator_map.keys())
        return CompilerSolution(
            status=CompilerStatus.INCOMPLETE,
            solver=SolverKind.GREEDY,
            solver_status=SolverStatus.INFEASIBLE,
            missing_predicates=missing,
            required_pair_count=len(universe),
        )
    selected_ids = set(operator_prerequisite_closure(required_ids, operator_map))
    covered = set(scheme_coverage(finite, selected_ids))
    dominated = dominated_operators(finite)
    candidates = [
        operator
        for operator in finite.operators
        if operator.id not in selected_ids and operator.id not in dominated
    ]
    iterations = 0
    while covered != universe:
        remaining = universe - covered
        scored: list[tuple[Decimal, int, Decimal, str, tuple[str, ...]]] = []
        for operator in candidates:
            closure = operator_prerequisite_closure(selected_ids | {operator.id}, operator_map)
            incremental = tuple(item for item in closure if item not in selected_ids)
            prospective = set(scheme_coverage(finite, set(closure)))
            benefit = len(prospective & remaining)
            if benefit == 0:
                continue
            cost = sum(
                (
                    weighted_cost(operator_map[item], finite.loaded.config.instability_weight)
                    for item in incremental
                ),
                start=Decimal(0),
            )
            ratio = Decimal("Infinity") if cost == 0 else Decimal(benefit) / cost
            scored.append((ratio, benefit, cost, operator.id, closure))
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
        _, _, _, _chosen_id, chosen_closure = min(
            scored,
            key=lambda item: (-item[0], -item[1], item[2], item[3]),
        )
        selected_ids.update(chosen_closure)
        covered = set(scheme_coverage(finite, selected_ids))
        candidates = [operator for operator in candidates if operator.id not in selected_ids]
        iterations += 1
    selected = [operator_map[item] for item in sorted(selected_ids)]
    from g2lc.compiler.counterexample import find_counterexample

    counterexample = find_counterexample(finite.loaded, sorted(selected_ids))
    if counterexample is not None:
        return CompilerSolution(
            status=CompilerStatus.INCOMPLETE,
            solver=SolverKind.GREEDY,
            solver_status=SolverStatus.INFEASIBLE,
            selected_operators=sorted(selected_ids),
            total_cost=scheme_cost(selected, finite.loaded.config.instability_weight),
            separated_pair_count=len(covered),
            required_pair_count=len(universe),
            iterations=iterations,
            counterexamples=[counterexample],
        )
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
