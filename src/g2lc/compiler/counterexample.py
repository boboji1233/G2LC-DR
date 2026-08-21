"""Z3 executability oracle and counterexample-separation exact solver."""

from __future__ import annotations

import z3
from ortools.sat.python import cp_model

from g2lc.compiler.exact import solve_lexicographic_model
from g2lc.compiler.problem import LoadedCompilerProblem
from g2lc.compiler.result import (
    CompilerSolution,
    CompilerStatus,
    Counterexample,
    SolverKind,
    SolverStatus,
)
from g2lc.errors import CompilationError
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
from g2lc.guidelines.evaluator import DecisionContext, action_signature, evaluate_guideline
from g2lc.ontology.models import (
    AtMostOneConstraint,
    ConditionalAllowedConstraint,
    DerivedEqualityConstraint,
    EvidenceCondition,
    ExactlyOneConstraint,
    ImplicationConstraint,
    MutualExclusionConstraint,
    ParentChildConstraint,
)
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


def _condition_to_z3(
    condition: EvidenceCondition,
    variables: dict[str, z3.ArithRef],
    indices: dict[str, dict[str, int]],
) -> z3.BoolRef:
    return (
        variables[condition.predicate] == indices[condition.predicate][scalar_key(condition.equals)]
    )


def _feasibility_constraints_z3(
    variables: dict[str, z3.ArithRef],
    problem: LoadedCompilerProblem,
    indices: dict[str, dict[str, int]],
) -> list[z3.BoolRef]:
    """Translate the complete finite feasibility contract without weakening it."""

    result: list[z3.BoolRef] = []
    for constraint in problem.ontology.feasibility.constraints:
        if isinstance(constraint, ImplicationConstraint):
            result.append(
                z3.Implies(
                    _condition_to_z3(constraint.antecedent, variables, indices),
                    _condition_to_z3(constraint.consequent, variables, indices),
                )
            )
        elif isinstance(constraint, MutualExclusionConstraint):
            terms = [_condition_to_z3(item, variables, indices) for item in constraint.conditions]
            result.append(z3.AtMost(*terms, 1))
        elif isinstance(constraint, ConditionalAllowedConstraint):
            allowed = z3.Or(
                *[
                    variables[constraint.predicate]
                    == indices[constraint.predicate][scalar_key(item)]
                    for item in constraint.allowed_values
                ]
            )
            result.append(
                z3.Implies(_condition_to_z3(constraint.antecedent, variables, indices), allowed)
            )
        elif isinstance(constraint, ExactlyOneConstraint):
            result.append(
                z3.PbEq(
                    [
                        (_condition_to_z3(item, variables, indices), 1)
                        for item in constraint.conditions
                    ],
                    1,
                )
            )
        elif isinstance(constraint, AtMostOneConstraint):
            terms = [_condition_to_z3(item, variables, indices) for item in constraint.conditions]
            result.append(z3.AtMost(*terms, 1))
        elif isinstance(constraint, DerivedEqualityConstraint):
            source_domain = problem.ontology.predicate(constraint.source_predicate).allowed_values
            target_indices = indices[constraint.target_predicate]
            cases = []
            for source_index, source_value in enumerate(source_domain):
                target_value = (
                    constraint.value_mapping[scalar_key(source_value)]
                    if constraint.value_mapping
                    else source_value
                )
                cases.append(
                    z3.And(
                        variables[constraint.source_predicate] == source_index,
                        variables[constraint.target_predicate]
                        == target_indices[scalar_key(target_value)],
                    )
                )
            result.append(z3.Or(*cases))
        elif isinstance(constraint, ParentChildConstraint):
            parent_active = z3.Or(
                *[
                    variables[constraint.parent_predicate]
                    == indices[constraint.parent_predicate][scalar_key(item)]
                    for item in constraint.when_parent_values
                ]
            )
            child_allowed = z3.Or(
                *[
                    variables[constraint.child_predicate]
                    == indices[constraint.child_predicate][scalar_key(item)]
                    for item in constraint.allowed_child_values
                ]
            )
            result.append(z3.Implies(parent_active, child_allowed))
        else:  # pragma: no cover - the discriminated union is exhaustive
            raise AssertionError(type(constraint).__name__)
    return result


def _derivation_constraints_z3(
    variables: dict[str, z3.ArithRef],
    problem: LoadedCompilerProblem,
    indices: dict[str, dict[str, int]],
) -> list[z3.BoolRef]:
    result: list[z3.BoolRef] = []
    for rule in problem.graph.rules:
        source_id = rule.input_predicates[0]
        target_id = rule.output_predicates[0]
        source_domain = problem.ontology.predicate(source_id).allowed_values
        cases = []
        for source_index, source_value in enumerate(source_domain):
            target_value = rule.value_mapping[scalar_key(source_value)]
            cases.append(
                z3.And(
                    variables[source_id] == source_index,
                    variables[target_id] == indices[target_id][scalar_key(target_value)],
                )
            )
        result.append(z3.Or(*cases))
    return result


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
    indices = _domain_index(problem)
    for operator in selected:
        left_requirements = [
            z3.Or(
                *[
                    left[item.predicate_id] == indices[item.predicate_id][scalar_key(value)]
                    for value in item.allowed_values
                ]
            )
            for item in operator.required_evidence_conditions
        ]
        right_requirements = [
            z3.Or(
                *[
                    right[item.predicate_id] == indices[item.predicate_id][scalar_key(value)]
                    for value in item.allowed_values
                ]
            )
            for item in operator.required_evidence_conditions
        ]
        left_applicable = z3.And(*left_requirements) if left_requirements else z3.BoolVal(True)
        right_applicable = z3.And(*right_requirements) if right_requirements else z3.BoolVal(True)
        equalities.append(left_applicable == right_applicable)
        for predicate_id in operator.output_predicates:
            mapping = operator.value_mappings.get(predicate_id)
            if mapping is None:
                observed_equal = left[predicate_id] == right[predicate_id]
            else:
                domain = problem.ontology.predicate(predicate_id).allowed_values
                observed_equal = _mapped_observation(
                    left[predicate_id], domain, mapping
                ) == _mapped_observation(right[predicate_id], domain, mapping)
            equalities.append(z3.Implies(left_applicable, observed_equal))
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
    indices = _domain_index(problem)
    solver.add(*_feasibility_constraints_z3(left, problem, indices))
    solver.add(*_feasibility_constraints_z3(right, problem, indices))
    solver.add(*_derivation_constraints_z3(left, problem, indices))
    solver.add(*_derivation_constraints_z3(right, problem, indices))
    solver.add(*_observation_equalities(selected, left, right, problem))
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
    decision_context = DecisionContext(
        ontology=problem.ontology,
        derivations=problem.graph,
        target_modalities=tuple(problem.config.target_modalities),
    )
    left_actions = {
        guideline.id: action_signature(
            evaluate_guideline(
                guideline,
                left_state,
                decision_context,
            )
        )
        for guideline in problem.guidelines
    }
    right_actions = {
        guideline.id: action_signature(
            evaluate_guideline(
                guideline,
                right_state,
                decision_context,
            )
        )
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


def find_feasible_state(problem: LoadedCompilerProblem) -> EvidenceState | None:
    """Return one legal complete evidence state, or ``None`` for an empty language."""

    variables = {
        predicate.id: z3.Int(f"witness__{predicate.id}")
        for predicate in problem.ontology.predicates
    }
    indices = _domain_index(problem)
    solver = z3.Solver()
    for predicate in problem.ontology.predicates:
        solver.add(variables[predicate.id] >= 0)
        solver.add(variables[predicate.id] < len(predicate.allowed_values))
    solver.add(*_feasibility_constraints_z3(variables, problem, indices))
    solver.add(*_derivation_constraints_z3(variables, problem, indices))
    status = solver.check()
    if status == z3.unknown:
        raise CompilationError(
            f"evidence-language satisfiability is unknown: {solver.reason_unknown()}"
        )
    if status != z3.sat:
        return None
    for predicate in sorted(problem.ontology.predicates, key=lambda item: item.id):
        for index in range(len(predicate.allowed_values)):
            solver.push()
            solver.add(variables[predicate.id] == index)
            candidate = solver.check()
            solver.pop()
            if candidate == z3.sat:
                solver.add(variables[predicate.id] == index)
                break
        else:  # pragma: no cover - the already-satisfiable prefix has a value
            raise CompilationError(
                f"cannot construct canonical evidence witness for {predicate.id!r}"
            )
    if solver.check() != z3.sat:  # pragma: no cover - guarded by the prefix checks
        raise CompilationError("canonical evidence witness unexpectedly became unsatisfiable")
    model = solver.model()
    return EvidenceState(
        values={
            predicate.id: predicate.allowed_values[
                model.eval(variables[predicate.id], model_completion=True).as_long()
            ]
            for predicate in problem.ontology.predicates
        }
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
    for operator in operators:
        for required_id in operator.required_operator_ids:
            if required_id not in variables:
                model.add(variables[operator.id] == 0)
            else:
                model.add(variables[operator.id] <= variables[required_id])
    return solve_lexicographic_model(
        model,
        variables,
        {
            operator.id: weighted_cost(operator, problem.config.instability_weight)
            for operator in operators
        },
        seed=problem.config.seed,
    )


def solve_counterexample_separation(
    problem: LoadedCompilerProblem,
    *,
    max_iterations: int = 1_000,
) -> CompilerSolution:
    """Iteratively add Z3 counterexamples to a restricted CP-SAT master."""

    if find_feasible_state(problem) is None:
        raise CompilationError("UNSAT_EVIDENCE_LANGUAGE: no legal complete state exists")
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
                solver_status=master_status,
                selected_operators=selected_ids,
                derived_predicates=sorted(exact_observed_predicates(selected, problem.graph)),
                total_cost=scheme_cost(selected, problem.config.instability_weight),
                optimal=master_status is SolverStatus.OPTIMAL,
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
