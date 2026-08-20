"""Minimum repair analysis for in-scope but unavailable evidence operators."""

from __future__ import annotations

from g2lc.compiler.exact import solve_exact
from g2lc.compiler.problem import FiniteProblem, LoadedCompilerProblem, build_finite_problem
from g2lc.compiler.result import CompilerSolution, CompilerStatus
from g2lc.operators.models import OperatorAvailability


def missing_predicates(finite: FiniteProblem) -> list[str]:
    """Identify changing guideline predicates in pairs no available operator separates."""

    referenced = finite.loaded.referenced_predicates()
    missing: set[str] = set()
    for pair_index, pair in enumerate(finite.pairs):
        if any(pair_index in finite.coverage[item.id] for item in finite.operators):
            continue
        left = finite.states[pair.left_index]
        right = finite.states[pair.right_index]
        missing.update(
            predicate_id
            for predicate_id in referenced
            if left.value(predicate_id) != right.value(predicate_id)
        )
    return sorted(missing)


def enrich_with_minimum_repair(
    loaded: LoadedCompilerProblem,
    finite: FiniteProblem,
    solution: CompilerSolution,
) -> CompilerSolution:
    """Solve an augmented catalogue and expose unavailable selections as repair items."""

    if solution.status is not CompilerStatus.INCOMPLETE:
        return solution
    repaired_finite = build_finite_problem(loaded, include_repair=True)
    repaired = solve_exact(repaired_finite)
    unavailable = {
        operator.id: operator
        for operator in repaired_finite.operators
        if operator.availability is not OperatorAvailability.AVAILABLE
    }
    additions = sorted(set(repaired.selected_operators) & unavailable.keys())
    repair_cost = round(sum(unavailable[item].cost for item in additions), 9)
    return solution.model_copy(
        update={
            "missing_predicates": missing_predicates(finite),
            "minimal_additions": additions,
            "minimum_repair_cost": repair_cost
            if repaired.status is CompilerStatus.EXECUTABLE
            else None,
        }
    )
