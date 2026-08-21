"""Minimum repair analysis for in-scope but unavailable evidence operators."""

from __future__ import annotations

import itertools
from decimal import Decimal

from ortools.sat.python import cp_model

from g2lc.compiler.exact import solve_lexicographic_model
from g2lc.compiler.problem import (
    FiniteProblem,
    LoadedCompilerProblem,
    build_finite_problem,
    scheme_coverage,
)
from g2lc.compiler.result import CompilerSolution, CompilerStatus, SolverStatus
from g2lc.errors import CompilationError
from g2lc.operators.cost import scheme_cost, weighted_cost
from g2lc.operators.lattice import operator_prerequisite_closure
from g2lc.operators.models import OperatorAvailability

BRUTE_FORCE_REPAIR_LIMIT = 18


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
    unavailable = {
        operator.id: operator
        for operator in repaired_finite.operators
        if operator.availability is not OperatorAvailability.AVAILABLE
    }
    available_ids = {
        item.id
        for item in repaired_finite.operators
        if item.availability is OperatorAvailability.AVAILABLE
    }
    base_coverage = set(scheme_coverage(repaired_finite, available_ids))
    universe = set(range(len(repaired_finite.pairs)))
    model = cp_model.CpModel()
    variables = {item: model.new_bool_var(item) for item in sorted(unavailable)}
    for pair_index in sorted(universe - base_coverage):
        separating = [
            variables[item]
            for item in sorted(unavailable)
            if pair_index in repaired_finite.coverage[item]
        ]
        if not separating:
            return solution.model_copy(update={"missing_predicates": missing_predicates(finite)})
        model.add(sum(separating) >= 1)
    all_operator_map = {item.id: item for item in repaired_finite.operators}
    for operator_id, variable in variables.items():
        for required_id in all_operator_map[operator_id].required_operator_ids:
            if required_id in available_ids:
                continue
            if required_id in variables:
                model.add(variable <= variables[required_id])
            else:
                model.add(variable == 0)
    selected_ids, repair_status = solve_lexicographic_model(
        model,
        variables,
        {
            item: weighted_cost(unavailable[item], loaded.config.instability_weight)
            for item in variables
        },
        seed=loaded.config.seed,
    )
    best: tuple[Decimal, int, tuple[str, ...]] | None = None
    if repair_status is not SolverStatus.INFEASIBLE:
        closure = operator_prerequisite_closure(available_ids | set(selected_ids), all_operator_map)
        additions = tuple(sorted(set(closure) - available_ids))
        if set(scheme_coverage(repaired_finite, set(closure))) != universe:
            raise CompilationError("CP-SAT repair candidate failed independent finite coverage")
        best = (
            scheme_cost(
                [all_operator_map[item] for item in additions],
                loaded.config.instability_weight,
            ),
            len(additions),
            additions,
        )

    if len(unavailable) <= BRUTE_FORCE_REPAIR_LIMIT:
        oracle: tuple[Decimal, int, tuple[str, ...]] | None = None
        for flags in itertools.product((False, True), repeat=len(unavailable)):
            ids = {
                item for item, selected in zip(sorted(unavailable), flags, strict=True) if selected
            }
            scheme = available_ids | ids
            closure_ids = set(operator_prerequisite_closure(scheme, all_operator_map))
            if closure_ids != scheme or set(scheme_coverage(repaired_finite, scheme)) != universe:
                continue
            cost = scheme_cost(
                [unavailable[item] for item in sorted(ids)],
                loaded.config.instability_weight,
            )
            key = (cost, len(ids), tuple(sorted(ids)))
            if oracle is None or key < oracle:
                oracle = key
        if oracle != best:
            raise CompilationError(
                f"CP-SAT incremental repair disagrees with brute-force oracle: {best} != {oracle}"
            )
    result_additions = list(best[2]) if best is not None else []
    repair_cost = best[0] if best is not None else None
    return solution.model_copy(
        update={
            "missing_predicates": missing_predicates(finite),
            "minimal_additions": result_additions,
            "minimum_repair_cost": repair_cost,
        }
    )


def enrich_with_symbolic_repair(
    loaded: LoadedCompilerProblem, solution: CompilerSolution
) -> CompilerSolution:
    """Compute INCOMPLETE explanations and incremental repair with symbolic queries."""

    if solution.status is not CompilerStatus.INCOMPLETE:
        return solution
    from g2lc.compiler.counterexample import find_counterexample

    available = loaded.available_operators()
    available_ids = {item.id for item in available}
    counterexamples = list(solution.counterexamples)
    if not counterexamples:
        witness = find_counterexample(loaded, sorted(available_ids))
        if witness is not None:
            counterexamples.append(witness)
    referenced = loaded.referenced_predicates()
    missing = sorted(
        {
            predicate
            for witness in counterexamples
            for predicate in referenced
            if witness.left.value(predicate) != witness.right.value(predicate)
        }
    )
    repair = {item.id: item for item in loaded.repair_operators()}
    if len(repair) > BRUTE_FORCE_REPAIR_LIMIT:
        raise CompilationError(
            "symbolic incremental repair exceeds the fail-closed brute-force limit "
            f"of {BRUTE_FORCE_REPAIR_LIMIT} unavailable operators"
        )
    all_operators = loaded.catalogue.operator_map()
    best: tuple[Decimal, int, tuple[str, ...]] | None = None
    for flags in itertools.product((False, True), repeat=len(repair)):
        additions = tuple(
            item for item, enabled in zip(sorted(repair), flags, strict=True) if enabled
        )
        scheme = available_ids | set(additions)
        if any(
            not set(all_operators[item].required_operator_ids).issubset(scheme) for item in scheme
        ):
            continue
        if find_counterexample(loaded, sorted(scheme)) is not None:
            continue
        key = (
            scheme_cost([repair[item] for item in additions], loaded.config.instability_weight),
            len(additions),
            additions,
        )
        if best is None or key < best:
            best = key
    return solution.model_copy(
        update={
            "counterexamples": counterexamples,
            "missing_predicates": missing,
            "minimal_additions": list(best[2]) if best is not None else [],
            "minimum_repair_cost": best[0] if best is not None else None,
        }
    )
