from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from g2lc.compiler.api import compile_problem
from g2lc.compiler.counterexample import find_counterexample
from g2lc.compiler.problem import build_finite_problem
from g2lc.compiler.result import CompilerStatus, SolverKind
from g2lc.guidelines.ast import Equals
from g2lc.guidelines.evaluator import evaluate_expression
from g2lc.guidelines.trivalued import TriValue, tri_and, tri_or
from g2lc.operators.derivation import distinguishes
from g2lc.types import EvidenceState

TRI = st.sampled_from(list(TriValue))
FAST = settings(max_examples=20, deadline=None)


@FAST
@given(TRI, TRI)
def test_and_is_commutative(left: TriValue, right: TriValue) -> None:
    assert tri_and([left, right]) is tri_and([right, left])


@FAST
@given(TRI, TRI)
def test_or_is_commutative(left: TriValue, right: TriValue) -> None:
    assert tri_or([left, right]) is tri_or([right, left])


@FAST
@given(TRI)
def test_double_negation(value: TriValue) -> None:
    assert ~~value is value


@FAST
@given(TRI)
def test_and_is_idempotent(value: TriValue) -> None:
    assert tri_and([value, value]) is value


@FAST
@given(TRI)
def test_or_is_idempotent(value: TriValue) -> None:
    assert tri_or([value, value]) is value


@FAST
@given(TRI, TRI, TRI)
def test_and_is_associative(a: TriValue, b: TriValue, c: TriValue) -> None:
    assert tri_and([tri_and([a, b]), c]) is tri_and([a, tri_and([b, c])])


@FAST
@given(TRI, TRI, TRI)
def test_or_is_associative(a: TriValue, b: TriValue, c: TriValue) -> None:
    assert tri_or([tri_or([a, b]), c]) is tri_or([a, tri_or([b, c])])


@FAST
@given(st.sampled_from(["gradable", "ma_presence", "hem_count_bin", "nv_presence"]))
def test_unknown_comparison_never_becomes_false(minimal_problem, predicate: str) -> None:  # type: ignore[no-untyped-def]
    value = minimal_problem.ontology.predicate(predicate).allowed_values[0]
    expression = Equals(predicate=predicate, value=value)
    assert (
        evaluate_expression(expression, EvidenceState(values={}), minimal_problem.ontology)
        is TriValue.UNKNOWN
    )


@settings(max_examples=12, deadline=None)
@given(
    st.sets(st.integers(min_value=0, max_value=6)), st.sets(st.integers(min_value=0, max_value=6))
)
def test_operator_coverage_is_monotone(minimal_problem, first: set[int], second: set[int]) -> None:  # type: ignore[no-untyped-def]
    finite = build_finite_problem(minimal_problem)
    operator_ids = [item.id for item in finite.operators]
    smaller_indices = first & set(range(len(operator_ids)))
    larger_indices = smaller_indices | (second & set(range(len(operator_ids))))
    smaller = (
        set().union(*(finite.coverage[operator_ids[index]] for index in smaller_indices))
        if smaller_indices
        else set()
    )
    larger = (
        set().union(*(finite.coverage[operator_ids[index]] for index in larger_indices))
        if larger_indices
        else set()
    )
    assert smaller.issubset(larger)


@settings(max_examples=10, deadline=None)
@given(st.sets(st.integers(min_value=0, max_value=6)))
def test_adding_operators_cannot_break_executability(minimal_problem, indices: set[int]) -> None:  # type: ignore[no-untyped-def]
    operator_ids = [item.id for item in minimal_problem.available_operators()]
    selected = sorted(operator_ids[index] for index in indices if index < len(operator_ids))
    complete = sorted(set(selected) | set(operator_ids))
    if find_counterexample(minimal_problem, selected) is None:
        assert find_counterexample(minimal_problem, complete) is None


@FAST
@given(st.sampled_from(["0", "1_3", "4_plus"]), st.sampled_from(["0", "1_3", "4_plus"]))
def test_presence_partition_matches_declared_mapping(
    minimal_problem, left: str, right: str
) -> None:  # type: ignore[no-untyped-def]
    operator = minimal_problem.catalogue.operator_map()["hem_presence_label"]
    left_state = EvidenceState(values={"hem_count_bin": left})
    right_state = EvidenceState(values={"hem_count_bin": right})
    expected = (left == "0") != (right == "0")
    assert distinguishes(operator, minimal_problem.graph, left_state, right_state) is expected


@settings(max_examples=5, deadline=None)
@given(st.integers(min_value=0, max_value=4))
def test_exact_never_costs_more_than_greedy(minimal_problem, _example: int) -> None:  # type: ignore[no-untyped-def]
    exact = compile_problem(minimal_problem, SolverKind.EXACT)
    greedy = compile_problem(minimal_problem, SolverKind.GREEDY)
    assert exact.status is CompilerStatus.EXECUTABLE
    assert greedy.status is CompilerStatus.EXECUTABLE
    assert exact.total_cost <= greedy.total_cost
