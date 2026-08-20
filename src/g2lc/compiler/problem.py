"""Project loading and finite action-separation problem construction."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pydantic import Field, ValidationError, field_validator

from g2lc.errors import CompilationError
from g2lc.guidelines.ast import Guideline, GuidelineBundle, guideline_predicates
from g2lc.guidelines.evaluator import action_signature, evaluate_guideline
from g2lc.guidelines.parser import load_guidelines
from g2lc.guidelines.validator import validate_guidelines
from g2lc.ontology.feasibility import feasible_completions, is_feasible_state
from g2lc.ontology.loader import load_ontology
from g2lc.ontology.models import (
    AtMostOneConstraint,
    ConditionalAllowedConstraint,
    DerivedEqualityConstraint,
    EvidenceOntology,
    ExactlyOneConstraint,
    ImplicationConstraint,
    MutualExclusionConstraint,
    ParentChildConstraint,
)
from g2lc.ontology.observability import find_observability_issues
from g2lc.operators.derivation import derivations_consistent, distinguishes_scheme
from g2lc.operators.lattice import (
    load_derivation_graph,
    load_operator_catalogue,
    operator_prerequisite_closure,
    validate_operators,
)
from g2lc.operators.models import (
    AnnotationOperator,
    DerivationGraph,
    OperatorAvailability,
    OperatorCatalogue,
)
from g2lc.types import EvidenceState, Modality, StrictModel
from g2lc.utils.io import load_yaml, resolve_from, validation_error


class CompilerProblem(StrictModel):
    """Portable path-based compiler configuration."""

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    ontology: str
    guidelines: list[str] = Field(min_length=1)
    operators: str
    derivations: str
    target_modalities: list[Modality] = Field(min_length=1)
    instability_weight: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)
    required_operators: list[str] = Field(default_factory=list)
    forbidden_operators: list[str] = Field(default_factory=list)
    max_states: int = Field(default=100_000, ge=1)
    seed: int = Field(default=0, ge=0)
    output: str = "certificate.json"

    @field_validator("required_operators", "forbidden_operators")
    @classmethod
    def unique_operator_constraints(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("operator constraint lists must be unique")
        return values


@dataclass(frozen=True)
class LoadedCompilerProblem:
    """Validated in-memory project plus authoritative source paths."""

    config_path: Path
    config: CompilerProblem
    ontology_path: Path
    guideline_paths: tuple[Path, ...]
    operator_path: Path
    derivation_path: Path
    ontology: EvidenceOntology
    guideline_bundles: tuple[GuidelineBundle, ...]
    guidelines: tuple[Guideline, ...]
    catalogue: OperatorCatalogue
    graph: DerivationGraph

    def referenced_predicates(self) -> set[str]:
        """Return all predicates used by all target guideline clauses."""

        return set().union(*(guideline_predicates(item) for item in self.guidelines))

    def available_operators(self) -> list[AnnotationOperator]:
        """Return project-selectable operators in deterministic order."""

        target_modalities = set(self.config.target_modalities)
        forbidden = set(self.config.forbidden_operators)
        candidates = {
            operator.id: operator
            for operator in self.catalogue.operators
            if operator.availability is OperatorAvailability.AVAILABLE
            and operator.id not in forbidden
            and set(operator.modalities).intersection(target_modalities)
            and set(operator.required_modalities).issubset(target_modalities)
        }
        changed = True
        while changed:
            changed = False
            for operator_id, operator in list(candidates.items()):
                if not set(operator.required_operator_ids).issubset(candidates):
                    del candidates[operator_id]
                    changed = True
        return sorted(candidates.values(), key=lambda item: item.id)

    def repair_operators(self) -> list[AnnotationOperator]:
        """Return modality-compatible unavailable operators usable only as suggestions."""

        target_modalities = set(self.config.target_modalities)
        return sorted(
            (
                operator
                for operator in self.catalogue.operators
                if operator.availability is not OperatorAvailability.AVAILABLE
                and set(operator.modalities).intersection(target_modalities)
                and set(operator.required_modalities).issubset(target_modalities)
            ),
            key=lambda item: item.id,
        )


@dataclass(frozen=True)
class StatePair:
    """One action-separating pair and the guidelines that distinguish it."""

    left_index: int
    right_index: int
    differing_guidelines: tuple[str, ...]


@dataclass(frozen=True)
class FiniteProblem:
    """Explicit small-state weighted test-cover instance."""

    loaded: LoadedCompilerProblem
    states: tuple[EvidenceState, ...]
    action_signatures: tuple[dict[str, str], ...]
    pairs: tuple[StatePair, ...]
    operators: tuple[AnnotationOperator, ...]
    coverage: dict[str, frozenset[int]]


def load_compiler_problem(path: str | Path) -> LoadedCompilerProblem:
    """Load all project sources while preserving OOS findings for compilation."""

    config_path = Path(path).resolve()
    try:
        config = CompilerProblem.model_validate(load_yaml(config_path))
    except ValidationError as exc:
        raise validation_error(config_path, exc) from exc

    ontology_path = resolve_from(config_path, config.ontology)
    guideline_paths = tuple(resolve_from(config_path, item) for item in config.guidelines)
    operator_path = resolve_from(config_path, config.operators)
    derivation_path = resolve_from(config_path, config.derivations)
    ontology = load_ontology(ontology_path)
    bundles = tuple(load_guidelines(item) for item in guideline_paths)
    for bundle in bundles:
        validate_guidelines(bundle)
    guidelines = tuple(guideline for bundle in bundles for guideline in bundle.guidelines)
    catalogue = load_operator_catalogue(operator_path)
    graph = load_derivation_graph(derivation_path)
    validate_operators(catalogue, graph, ontology)

    operator_ids = catalogue.operator_map().keys()
    unknown_constraints = sorted(
        (set(config.required_operators) | set(config.forbidden_operators)) - operator_ids
    )
    if unknown_constraints:
        raise CompilationError(f"project constrains unknown operators {unknown_constraints}")
    overlap = sorted(set(config.required_operators) & set(config.forbidden_operators))
    if overlap:
        raise CompilationError(f"operators cannot be both required and forbidden: {overlap}")

    loaded = LoadedCompilerProblem(
        config_path=config_path,
        config=config,
        ontology_path=ontology_path,
        guideline_paths=guideline_paths,
        operator_path=operator_path,
        derivation_path=derivation_path,
        ontology=ontology,
        guideline_bundles=bundles,
        guidelines=guidelines,
        catalogue=catalogue,
        graph=graph,
    )
    if not preflight_oos(loaded):
        for bundle in bundles:
            validate_guidelines(bundle, ontology, graph)
    return loaded


def preflight_oos(
    problem: LoadedCompilerProblem,
) -> list[tuple[str, str, tuple[str, ...], list[str]]]:
    """Return predicate, reason, modalities and source clauses for OOS evidence."""

    issues = find_observability_issues(
        problem.ontology,
        problem.referenced_predicates(),
        set(problem.config.target_modalities),
    )
    clauses: dict[str, list[str]] = {}
    for guideline in problem.guidelines:
        for rule in guideline.rules:
            for predicate_id in guideline_predicates(
                guideline.model_copy(update={"rules": [rule]})
            ):
                clauses.setdefault(predicate_id, []).append(f"{guideline.id}:{rule.id}")
    return [
        (
            issue.predicate_id,
            issue.reason,
            issue.required_modalities,
            sorted(clauses.get(issue.predicate_id, [])),
        )
        for issue in issues
    ]


def enumerate_states(problem: LoadedCompilerProblem) -> tuple[EvidenceState, ...]:
    """Enumerate complete finite evidence states under the declared ontology."""

    predicates = sorted(problem.ontology.predicates, key=lambda item: item.id)
    state_count = math.prod(len(predicate.allowed_values) for predicate in predicates)
    if state_count > problem.config.max_states:
        raise CompilationError(
            f"finite state space has {state_count} states, exceeding max_states="
            f"{problem.config.max_states}; use the separation solver or reduce the language"
        )
    states = (
        EvidenceState(
            values={
                predicate.id: value for predicate, value in zip(predicates, values, strict=True)
            }
        )
        for values in itertools.product(*(predicate.allowed_values for predicate in predicates))
    )
    return tuple(
        state
        for state in states
        if is_feasible_state(state, problem.ontology, complete=True)
        and derivations_consistent(state, problem.graph)
    )


def _constraint_predicates(constraint: object) -> set[str]:
    if isinstance(constraint, ImplicationConstraint):
        return {constraint.antecedent.predicate, constraint.consequent.predicate}
    if isinstance(
        constraint,
        (MutualExclusionConstraint, ExactlyOneConstraint, AtMostOneConstraint),
    ):
        return {item.predicate for item in constraint.conditions}
    if isinstance(constraint, ConditionalAllowedConstraint):
        return {constraint.antecedent.predicate, constraint.predicate}
    if isinstance(constraint, DerivedEqualityConstraint):
        return {constraint.source_predicate, constraint.target_predicate}
    if isinstance(constraint, ParentChildConstraint):
        return {constraint.parent_predicate, constraint.child_predicate}
    raise AssertionError(type(constraint).__name__)


def relevant_predicate_closure(problem: LoadedCompilerProblem) -> tuple[str, ...]:
    """Return the sound decision/feasibility/derivation/operator dependency closure."""

    closure = set(problem.referenced_predicates())
    operator_map = problem.catalogue.operator_map()
    required_ids = operator_prerequisite_closure(
        problem.config.required_operators,
        operator_map,
    )
    for operator_id in required_ids:
        required_operator = operator_map[operator_id]
        closure.update(required_operator.output_predicates)
        closure.update(item.predicate_id for item in required_operator.required_evidence_conditions)
    changed = True
    while changed:
        before = set(closure)
        for constraint in problem.ontology.feasibility.constraints:
            predicates = _constraint_predicates(constraint)
            if predicates & closure:
                closure.update(predicates)
        for rule in problem.graph.rules:
            predicates = set(rule.input_predicates) | set(rule.output_predicates)
            if predicates & closure:
                closure.update(predicates)
        for operator in problem.catalogue.operators:
            outputs = set(operator.output_predicates)
            if not outputs & closure:
                continue
            closure.update(item.predicate_id for item in operator.required_evidence_conditions)
            prerequisite_ids = operator_prerequisite_closure(
                operator.required_operator_ids,
                operator_map,
            )
            for prerequisite_id in prerequisite_ids:
                prerequisite = operator_map[prerequisite_id]
                closure.update(prerequisite.output_predicates)
                closure.update(
                    item.predicate_id for item in prerequisite.required_evidence_conditions
                )
        changed = closure != before
    return tuple(sorted(closure))


def enumerate_relevant_states(problem: LoadedCompilerProblem) -> tuple[EvidenceState, ...]:
    """Enumerate feasible decision-relevant projections without unrelated dimensions."""

    predicate_ids = relevant_predicate_closure(problem)
    predicates = [problem.ontology.predicate(item) for item in predicate_ids]
    state_count = math.prod(len(item.allowed_values) for item in predicates)
    if state_count > problem.config.max_states:
        raise CompilationError(
            f"relevant finite state space has {state_count} states, exceeding "
            f"max_states={problem.config.max_states}"
        )
    result: list[EvidenceState] = []
    for values in itertools.product(*(item.allowed_values for item in predicates)):
        projected = EvidenceState(
            values={item.id: value for item, value in zip(predicates, values, strict=True)}
        )
        if next(feasible_completions(projected, problem.ontology, problem.graph), None) is not None:
            result.append(projected)
    if not result:
        raise CompilationError("UNSAT_EVIDENCE_LANGUAGE: no legal complete state exists")
    return tuple(result)


def build_finite_problem(
    loaded: LoadedCompilerProblem,
    *,
    include_repair: bool = False,
    relevant_only: bool = False,
) -> FiniteProblem:
    """Construct the exact action-separating state-pair universe."""

    if preflight_oos(loaded):
        raise CompilationError("cannot build a finite compiler problem with OOS predicates")
    states = enumerate_relevant_states(loaded) if relevant_only else enumerate_states(loaded)
    if not states:
        raise CompilationError("UNSAT_EVIDENCE_LANGUAGE: no legal complete state exists")
    action_rows: list[dict[str, str]] = []
    for state in states:
        action_rows.append(
            {
                guideline.id: action_signature(
                    evaluate_guideline(
                        guideline,
                        state,
                        loaded.ontology,
                        derivations=loaded.graph,
                    )
                )
                for guideline in loaded.guidelines
            }
        )
    pairs: list[StatePair] = []
    for left_index in range(len(states)):
        for right_index in range(left_index + 1, len(states)):
            differing = tuple(
                sorted(
                    guideline.id
                    for guideline in loaded.guidelines
                    if action_rows[left_index][guideline.id]
                    != action_rows[right_index][guideline.id]
                )
            )
            if differing:
                pairs.append(StatePair(left_index, right_index, differing))
    operators = loaded.available_operators()
    if include_repair:
        operators = sorted([*operators, *loaded.repair_operators()], key=lambda item: item.id)
    if relevant_only:
        relevant = set(relevant_predicate_closure(loaded))
        required_ids = set(
            operator_prerequisite_closure(
                loaded.config.required_operators,
                loaded.catalogue.operator_map(),
            )
        )
        operators = [
            item
            for item in operators
            if item.id in required_ids or set(item.output_predicates) & relevant
        ]
    coverage: dict[str, frozenset[int]] = {}
    operator_map = {item.id: item for item in operators}
    for operator in operators:
        closure_ids = operator_prerequisite_closure([operator.id], operator_map)
        closure = [operator_map[item] for item in closure_ids]
        coverage[operator.id] = frozenset(
            pair_index
            for pair_index, pair in enumerate(pairs)
            if distinguishes_scheme(
                closure, loaded.graph, states[pair.left_index], states[pair.right_index]
            )
        )
    return FiniteProblem(
        loaded=loaded,
        states=states,
        action_signatures=tuple(action_rows),
        pairs=tuple(pairs),
        operators=tuple(operators),
        coverage=coverage,
    )


def scheme_coverage(finite: FiniteProblem, selected_ids: set[str]) -> frozenset[int]:
    """Return coverage for a complete prerequisite-closed Stage-1.5 scheme."""

    operator_map = {item.id: item for item in finite.operators}
    closure = operator_prerequisite_closure(selected_ids, operator_map)
    if not closure:
        return frozenset()
    return frozenset().union(*(finite.coverage[item] for item in closure))


def make_counterexample(
    finite: FiniteProblem, pair_index: int
) -> tuple[EvidenceState, EvidenceState, StatePair]:
    """Resolve an explicit pair index into its two states."""

    pair = finite.pairs[pair_index]
    return finite.states[pair.left_index], finite.states[pair.right_index], pair
