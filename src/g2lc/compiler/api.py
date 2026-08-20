"""Public compiler orchestration without CLI or serialization concerns."""

from __future__ import annotations

from g2lc.compiler.counterexample import find_feasible_state, solve_counterexample_separation
from g2lc.compiler.exact import solve_exact
from g2lc.compiler.greedy import solve_greedy
from g2lc.compiler.problem import (
    LoadedCompilerProblem,
    build_finite_problem,
    preflight_oos,
)
from g2lc.compiler.repair import enrich_with_minimum_repair, enrich_with_symbolic_repair
from g2lc.compiler.result import (
    CompilerSolution,
    CompilerStatus,
    OutOfSpecFinding,
    SolverKind,
    SolverStatus,
)


def compile_problem(
    loaded: LoadedCompilerProblem,
    solver: SolverKind,
) -> CompilerSolution:
    """Compile a loaded project into a scientific outcome."""

    if find_feasible_state(loaded) is None:
        return CompilerSolution(
            status=CompilerStatus.UNSAT_EVIDENCE_LANGUAGE,
            solver=solver,
            solver_status=SolverStatus.INFEASIBLE,
        )
    issues = preflight_oos(loaded)
    if issues:
        return CompilerSolution(
            status=CompilerStatus.OUT_OF_SPEC,
            solver=solver,
            solver_status=SolverStatus.INFEASIBLE,
            out_of_spec=[
                OutOfSpecFinding(
                    predicate_id=predicate_id,
                    reason=reason,
                    required_modalities=list(modalities),
                    source_clauses=clauses,
                )
                for predicate_id, reason, modalities, clauses in issues
            ],
        )
    if solver is SolverKind.SEPARATION:
        solution = solve_counterexample_separation(loaded)
        return enrich_with_symbolic_repair(loaded, solution).model_copy(
            update={"required_pair_count": None}
        )
    finite = build_finite_problem(loaded)
    solution = solve_exact(finite) if solver is SolverKind.EXACT else solve_greedy(finite)
    return enrich_with_minimum_repair(loaded, finite, solution)
