from __future__ import annotations

from g2lc.compiler.api import compile_problem
from g2lc.compiler.counterexample import find_counterexample
from g2lc.compiler.dominance import dominated_operators
from g2lc.compiler.exact import brute_force_optimum, solve_exact
from g2lc.compiler.problem import build_finite_problem, enumerate_states, preflight_oos
from g2lc.compiler.result import CompilerStatus, SolverKind, SolverStatus

EXPECTED = [
    "hem_count_bin_label",
    "ma_presence_label",
    "nv_presence_label",
    "quality_label",
]


def test_finite_state_count(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    assert len(enumerate_states(minimal_problem)) == 24


def test_exact_known_optimum(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    solution = solve_exact(build_finite_problem(minimal_problem))
    assert solution.status is CompilerStatus.EXECUTABLE
    assert solution.selected_operators == EXPECTED
    assert solution.total_cost == 5.0
    assert solution.solver_status is SolverStatus.OPTIMAL


def test_exact_equals_bruteforce(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    finite = build_finite_problem(minimal_problem)
    exact = solve_exact(finite)
    brute = brute_force_optimum(finite)
    assert brute == (EXPECTED, 5.0)
    assert exact.total_cost == brute[1]


def test_greedy_is_executable(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    solution = compile_problem(minimal_problem, SolverKind.GREEDY)
    assert solution.status is CompilerStatus.EXECUTABLE
    assert find_counterexample(minimal_problem, solution.selected_operators) is None


def test_separation_solver_is_exact(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    solution = compile_problem(minimal_problem, SolverKind.SEPARATION)
    assert solution.status is CompilerStatus.EXECUTABLE
    assert solution.optimal is True
    assert solution.total_cost == 5.0
    assert find_counterexample(minimal_problem, solution.selected_operators) is None


def test_empty_scheme_has_counterexample(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    assert find_counterexample(minimal_problem, []) is not None


def test_complete_scheme_has_no_counterexample(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    assert find_counterexample(minimal_problem, EXPECTED) is None


def test_missing_fixture_exact_repair(missing_problem) -> None:  # type: ignore[no-untyped-def]
    solution = compile_problem(missing_problem, SolverKind.EXACT)
    assert solution.status is CompilerStatus.INCOMPLETE
    assert solution.missing_predicates == ["nv_presence"]
    assert solution.minimal_additions == ["nv_presence_label"]
    assert solution.minimum_repair_cost == 1.5


def test_oos_fixture_reports_modality(oos_problem) -> None:  # type: ignore[no-untyped-def]
    solution = compile_problem(oos_problem, SolverKind.EXACT)
    assert solution.status is CompilerStatus.OUT_OF_SPEC
    assert solution.out_of_spec[0].predicate_id == "oct_central_thickness"
    assert solution.out_of_spec[0].required_modalities == ["OCT"]
    assert preflight_oos(oos_problem)


def test_dominated_operator_detected(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    dominated = dominated_operators(build_finite_problem(minimal_problem))
    assert dominated["hem_full_mask"] == "hem_count_bin_label"
    assert "hem_count_bin_label" not in dominated


def test_same_seed_is_deterministic(minimal_problem) -> None:  # type: ignore[no-untyped-def]
    finite = build_finite_problem(minimal_problem)
    assert solve_exact(finite).model_dump() == solve_exact(finite).model_dump()
