"""Project loading and finite action-separation problem construction."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, ValidationError, field_validator

from g2lc.errors import CompilationError
from g2lc.guidelines.ast import Guideline, GuidelineBundle, guideline_predicates
from g2lc.guidelines.evaluator import action_signature, evaluate_guideline
from g2lc.guidelines.parser import load_guidelines
from g2lc.guidelines.validator import validate_guidelines
from g2lc.ontology.loader import load_ontology
from g2lc.ontology.models import EvidenceOntology
from g2lc.ontology.observability import find_observability_issues
from g2lc.operators.derivation import distinguishes
from g2lc.operators.lattice import (
    load_derivation_graph,
    load_operator_catalogue,
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
    instability_weight: float = Field(default=0, ge=0, allow_inf_nan=False)
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
        return sorted(
            (
                operator
                for operator in self.catalogue.operators
                if operator.availability is OperatorAvailability.AVAILABLE
                and operator.id not in forbidden
                and set(operator.modalities).intersection(target_modalities)
            ),
            key=lambda item: item.id,
        )

    def repair_operators(self) -> list[AnnotationOperator]:
        """Return modality-compatible unavailable operators usable only as suggestions."""

        target_modalities = set(self.config.target_modalities)
        return sorted(
            (
                operator
                for operator in self.catalogue.operators
                if operator.availability is not OperatorAvailability.AVAILABLE
                and set(operator.modalities).intersection(target_modalities)
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
            validate_guidelines(bundle, ontology)
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
    return tuple(
        EvidenceState(
            values={
                predicate.id: value for predicate, value in zip(predicates, values, strict=True)
            }
        )
        for values in itertools.product(*(predicate.allowed_values for predicate in predicates))
    )


def build_finite_problem(
    loaded: LoadedCompilerProblem,
    *,
    include_repair: bool = False,
) -> FiniteProblem:
    """Construct the exact action-separating state-pair universe."""

    if preflight_oos(loaded):
        raise CompilationError("cannot build a finite compiler problem with OOS predicates")
    states = enumerate_states(loaded)
    action_rows: list[dict[str, str]] = []
    for state in states:
        action_rows.append(
            {
                guideline.id: action_signature(
                    evaluate_guideline(guideline, state, loaded.ontology)
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
    coverage: dict[str, frozenset[int]] = {}
    for operator in operators:
        coverage[operator.id] = frozenset(
            pair_index
            for pair_index, pair in enumerate(pairs)
            if distinguishes(
                operator,
                loaded.graph,
                states[pair.left_index],
                states[pair.right_index],
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


def make_counterexample(
    finite: FiniteProblem, pair_index: int
) -> tuple[EvidenceState, EvidenceState, StatePair]:
    """Resolve an explicit pair index into its two states."""

    pair = finite.pairs[pair_index]
    return finite.states[pair.left_index], finite.states[pair.right_index], pair
