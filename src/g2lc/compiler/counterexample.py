"""Z3 executability oracle and counterexample-separation exact solver."""

from __future__ import annotations

import z3
from ortools.sat.python import cp_model

from g2lc.compiler.exact import _units
from g2lc.compiler.problem import LoadedCompilerProblem
from g2lc.compiler.result import (
    CompilerSolution,
    CompilerStatus,
    Counterexample,
    SolverKind,
    SolverStatus,
)
from g2lc.guidelines.ast import (
    And,
    Equals,
    Expression,
    GreaterEqual,
    Guideline,
    InSet,
    Known,
    LessEqual,
    Not,
    Or,
)
from g2lc.guidelines.evaluator import action_signature, evaluate_guideline
from g2lc.operators.cost import scheme_cost, weighted_cost
from g2lc.operators.derivation import distinguishes, exact_observed_predicates
from g2lc.operators.models import AnnotationOperator
from g2lc.types import EvidenceState, JsonScalar, scalar_key
from g2lc.utils.io import canonical_json


def _domain_index(problem: LoadedCompilerProblem) -> dict[str, dict[str, int]]:
    return {
        predicate.id: {
            scalar_key(value): index for index, value in enumerate(predicate.allowed_values)
        }
        for predicate in problem.ontology.predicates
    }


def _expression_to_z3(
    expression: Expression,
    variables: dict[str, z3.ArithRef],
    problem: LoadedCompilerProblem,
    indices: dict[str, dict[str, int]],
) -> z3.BoolRef:
    if isinstance(expression, And):
        return z3.And(
            *[_expression_to_z3(term, variables, problem, indices) for term in expression.terms]
        )
    if isinstance(expression, Or):
        return z3.Or(
            *[_expression_to_z3(term, variables, problem, indices) for term in expression.terms]
        )
    if isinstance(expression, Not):
        return z3.Not(_expression_to_z3(expression.term, variables, problem, indices))
    if isinstance(expression, Known):
        return z3.BoolVal(True)
    variable = variables[expression.predicate]
    predicate = problem.ontology.predicate(expression.predicate)
    if isinstance(expression, Equals):
        return variable == indices[expression.predicate][scalar_key(expression.value)]
    if isinstance(expression, InSet):
        return z3.Or(
            *[
                variable == indices[expression.predicate][scalar_key(value)]
                for value in expression.values
            ]
        )
    if isinstance(expression, (GreaterEqual, LessEqual)):
        allowed: list[int] = []
        for index, value in enumerate(predicate.allowed_values):
            assert isinstance(value, (int, float)) and not isinstance(value, bool)
            greater_match = isinstance(expression, GreaterEqual) and value >= expression.value
            lesser_match = isinstance(expression, LessEqual) and value <= expression.value
            if greater_match or lesser_match:
                allowed.append(index)
        return z3.Or(*[variable == index for index in allowed])
    raise AssertionError(f"unhandled expression {type(expression).__name__}")


def _guideline_action_z3(
    guideline: Guideline,
    variables: dict[str, z3.ArithRef],
    problem: LoadedCompilerProblem,
    indices: dict[str, dict[str, int]],
) -> z3.ArithRef:
    action_keys = sorted(
        {canonical_json(rule.action.model_dump(mode="json")) for rule in guideline.rules}
        | (
            {canonical_json(guideline.default_action.model_dump(mode="json"))}
            if guideline.default_action is not None
            else set()
        )
    )
    action_index = {key: index for index, key in enumerate(action_keys)}
    default: z3.ArithRef = z3.IntVal(-1)
    if guideline.default_action is not None:
        default = z3.IntVal(
            action_index[canonical_json(guideline.default_action.model_dump(mode="json"))]
        )
    result = default
    rules = sorted(guideline.rules, key=lambda item: (-item.priority, item.id))
    for rule in reversed(rules):
        key = canonical_json(rule.action.model_dump(mode="json"))
        result = z3.If(
            _expression_to_z3(rule.when, variables, problem, indices),
            z3.IntVal(action_index[key]),
            result,
        )
    return result


def _mapped_observation(
    variable: z3.ArithRef,
    domain: list[JsonScalar],
    mapping: dict[str, JsonScalar],
) -> z3.ArithRef:
    output_values = sorted({scalar_key(value) for value in mapping.values()})
    output_indices = {value: index for index, value in enumerate(output_values)}
    result: z3.ArithRef = z3.IntVal(-1)
    for index in reversed(range(len(domain))):
        observed = output_indices[scalar_key(mapping[scalar_key(domain[index])])]
        result = z3.If(variable == index, z3.IntVal(observed), result)
    return result


def _observation_equalities(
    selected: list[AnnotationOperator],
    left: dict[str, z3.ArithRef],
    right: dict[str, z3.ArithRef],
    problem: LoadedCompilerProblem,
) -> list[z3.BoolRef]:
    equalities: list[z3.BoolRef] = []
    for operator in selected:
        for predicate_id in operator.output_predicates:
            mapping = operator.value_mappings.get(predicate_id)
            if mapping is None:
                equalities.append(left[predicate_id] == right[predicate_id])
            else:
                domain = problem.ontology.predicate(predicate_id).allowed_values
                equalities.append(
                    _mapped_observation(left[predicate_id], domain, mapping)
                    == _mapped_observation(right[predicate_id], domain, mapping)
                )
    for predicate_id in exact_observed_predicates(selected, problem.graph):
        equalities.append(left[predicate_id] == right[predicate_id])
    return equalities


def find_counterexample(
    problem: LoadedCompilerProblem,
    selected_operator_ids: list[str],
) -> Counterexample | None:
    """Ask Z3 for two indistinguishable complete states with different actions."""

    operator_map = problem.catalogue.operator_map()
    selected = [operator_map[item] for item in sorted(selected_operator_ids)]
    left = {
        predicate.id: z3.Int(f"left__{predicate.id}") for predicate in problem.ontology.predicates
    }
    right = {
        predicate.id: z3.Int(f"right__{predicate.id}") for predicate in problem.ontology.predicates
    }
    solver = z3.Solver()
    for predicate in problem.ontology.predicates:
        solver.add(left[predicate.id] >= 0, left[predicate.id] < len(predicate.allowed_values))
        solver.add(right[predicate.id] >= 0, right[predicate.id] < len(predicate.allowed_values))
    solver.add(*_observation_equalities(selected, left, right, problem))
    indices = _domain_index(problem)
    action_differences = []
    for guideline in problem.guidelines:
        action_differences.append(
            _guideline_action_z3(guideline, left, problem, indices)
            != _guideline_action_z3(guideline, right, problem, indices)
        )
    solver.add(z3.Or(*action_differences))
    if solver.check() != z3.sat:
        return None
    model = solver.model()

    def state_from(variables: dict[str, z3.ArithRef]) -> EvidenceState:
        values: dict[str, JsonScalar] = {}
        for predicate in problem.ontology.predicates:
            index = model.eval(variables[predicate.id], model_completion=True).as_long()
            values[predicate.id] = predicate.allowed_values[index]
        return EvidenceState(values=values)

    left_state = state_from(left)
    right_state = state_from(right)
    left_actions = {
        guideline.id: action_signature(evaluate_guideline(guideline, left_state, problem.ontology))
        for guideline in problem.guidelines
    }
    right_actions = {
        guideline.id: action_signature(evaluate_guideline(guideline, right_state, problem.ontology))
        for guideline in problem.guidelines
    }
    differing = sorted(
        guideline.id
        for guideline in problem.guidelines
        if left_actions[guideline.id] != right_actions[guideline.id]
    )
    return Counterexample(
        left=left_state,
        right=right_state,
        differing_guidelines=differing,
        left_actions={item: left_actions[item] for item in differing},
        right_actions={item: right_actions[item] for item in differing},
    )


def _solve_master(
    problem: LoadedCompilerProblem,
    operators: list[AnnotationOperator],
    constraints: list[set[str]],
) -> tuple[list[str], SolverStatus]:
    model = cp_model.CpModel()
    variables = {operator.id: model.new_bool_var(operator.id) for operator in operators}
    for separating in constraints:
        model.add(sum(variables[item] for item in sorted(separating)) >= 1)
    for operator_id in sorted(problem.config.required_operators):
        if operator_id not in variables:
            return [], SolverStatus.INFEASIBLE
        model.add(variables[operator_id] == 1)
    count_factor = len(operators) + 1
    model.minimize(
        sum(
            (_units(weighted_cost(operator, problem.config.instability_weight)) * count_factor + 1)
            * variables[operator.id]
            for operator in operators
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = problem.config.seed
    status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return [], SolverStatus.INFEASIBLE
    return (
        sorted(operator.id for operator in operators if solver.value(variables[operator.id])),
        SolverStatus.OPTIMAL if status == cp_model.OPTIMAL else SolverStatus.FEASIBLE,
    )


def solve_counterexample_separation(
    problem: LoadedCompilerProblem,
    *,
    max_iterations: int = 1_000,
) -> CompilerSolution:
    """Iteratively add Z3 counterexamples to a restricted CP-SAT master."""

    operators = problem.available_operators()
    constraints: list[set[str]] = []
    seen: set[str] = set()
    for iteration in range(max_iterations + 1):
        selected_ids, master_status = _solve_master(problem, operators, constraints)
        if master_status is SolverStatus.INFEASIBLE:
            return CompilerSolution(
                status=CompilerStatus.INCOMPLETE,
                solver=SolverKind.SEPARATION,
                solver_status=master_status,
                iterations=iteration,
            )
        counterexample = find_counterexample(problem, selected_ids)
        if counterexample is None:
            operator_map = {operator.id: operator for operator in operators}
            selected = [operator_map[item] for item in selected_ids]
            return CompilerSolution(
                status=CompilerStatus.EXECUTABLE,
                solver=SolverKind.SEPARATION,
                solver_status=SolverStatus.OPTIMAL,
                selected_operators=selected_ids,
                derived_predicates=sorted(exact_observed_predicates(selected, problem.graph)),
                total_cost=scheme_cost(selected, problem.config.instability_weight),
                optimal=True,
                separated_pair_count=len(constraints),
                required_pair_count=len(constraints),
                iterations=iteration + 1,
            )
        ce_key = canonical_json(counterexample.model_dump(mode="json"))
        if ce_key in seen:
            return CompilerSolution(
                status=CompilerStatus.INCOMPLETE,
                solver=SolverKind.SEPARATION,
                solver_status=SolverStatus.INFEASIBLE,
                iterations=iteration + 1,
                counterexamples=[counterexample],
            )
        seen.add(ce_key)
        separating = {
            operator.id
            for operator in operators
            if distinguishes(operator, problem.graph, counterexample.left, counterexample.right)
        }
        if not separating:
            missing = sorted(
                predicate_id
                for predicate_id in problem.referenced_predicates()
                if counterexample.left.value(predicate_id)
                != counterexample.right.value(predicate_id)
            )
            return CompilerSolution(
                status=CompilerStatus.INCOMPLETE,
                solver=SolverKind.SEPARATION,
                solver_status=SolverStatus.INFEASIBLE,
                iterations=iteration + 1,
                counterexamples=[counterexample],
                missing_predicates=missing,
            )
        constraints.append(separating)
    return CompilerSolution(
        status=CompilerStatus.INCOMPLETE,
        solver=SolverKind.SEPARATION,
        solver_status=SolverStatus.LIMIT_REACHED,
        iterations=max_iterations,
    )
