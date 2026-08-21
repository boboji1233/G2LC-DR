"""Reproduce the Stage 1.6 semantic defects against the immutable baseline checkout.

Run this script with ``PYTHONPATH`` pointing at the baseline checkout's ``src``
directory.  Exit status 1 is the expected result: it means every named baseline
defect was observed.  Exit status 2 means the probe itself could not run.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from g2lc.compiler.api import compile_problem
from g2lc.compiler.problem import load_compiler_problem
from g2lc.compiler.result import SolverKind
from g2lc.errors import GuidelineValidationError, OntologyValidationError
from g2lc.guidelines.ast import ClinicalAction, Equals
from g2lc.guidelines.evaluator import evaluate_guideline
from g2lc.guidelines.validator import validate_guidelines
from g2lc.ontology.models import FeasibilityProgram
from g2lc.ontology.validator import validate_ontology
from g2lc.types import EvidenceState

BASELINE_COMMIT = "ec3250d7e3dba0379c3b5205949c23e4f4ee5d59"


def _greedy_prerequisite(problem: Any) -> dict[str, Any]:
    guideline = problem.guidelines[0]
    rule = guideline.rules[0].model_copy(
        update={
            "id": "ma_action",
            "priority": 10,
            "when": Equals(predicate="ma_presence", value="present"),
            "action": ClinicalAction(values={"decision": "refer"}),
        }
    )
    changed_guideline = guideline.model_copy(
        update={
            "id": "ma_only",
            "rules": [rule],
            "default_action": ClinicalAction(values={"decision": "routine"}),
        }
    )
    operator_map = problem.catalogue.operator_map()
    prerequisite = operator_map["quality_label"].model_copy(update={"cost": Decimal("2.0")})
    label = operator_map["ma_presence_label"].model_copy(
        update={
            "cost": Decimal("0.1"),
            "required_operator_ids": ["quality_label"],
            "required_evidence_conditions": [],
        }
    )
    changed = replace(
        problem,
        guidelines=(changed_guideline,),
        catalogue=problem.catalogue.model_copy(update={"operators": [prerequisite, label]}),
        config=problem.config.model_copy(update={"required_operators": []}),
    )
    solution = compile_problem(changed, SolverKind.GREEDY)
    expected = ["ma_presence_label", "quality_label"]
    actual = solution.selected_operators
    return {
        "defect_observed": actual != expected or solution.total_cost != Decimal("2.1"),
        "expected_selected": expected,
        "actual_selected": actual,
        "expected_cost": "2.1",
        "actual_cost": str(solution.total_cost),
    }


def _finite_feasibility(problem: Any) -> dict[str, Any]:
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
                {
                    "kind": "mutual_exclusion",
                    "conditions": [
                        {"predicate": "ma_presence", "equals": "present"},
                        {"predicate": "nv_presence", "equals": "present"},
                    ],
                }
            ],
        }
    )
    ontology = problem.ontology.model_copy(update={"feasibility": program})
    guideline = problem.guidelines[0]
    first = guideline.rules[0].model_copy(
        update={
            "id": "ma_action",
            "priority": 10,
            "when": Equals(predicate="ma_presence", value="present"),
            "action": ClinicalAction(values={"decision": "a"}),
        }
    )
    second = guideline.rules[1].model_copy(
        update={
            "id": "nv_action",
            "priority": 10,
            "when": Equals(predicate="nv_presence", value="present"),
            "action": ClinicalAction(values={"decision": "b"}),
        }
    )
    bundle = problem.guideline_bundles[0].model_copy(
        update={"guidelines": [guideline.model_copy(update={"rules": [first, second]})]}
    )
    try:
        validate_guidelines(bundle, ontology, conflict_state_limit=10_000)
    except GuidelineValidationError as exc:
        return {"defect_observed": True, "actual": type(exc).__name__, "message": str(exc)}
    return {"defect_observed": False, "actual": "accepted"}


def _empty_language(problem: Any) -> dict[str, Any]:
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
                {
                    "kind": "implication",
                    "if": {"predicate": "gradable", "equals": "yes"},
                    "then": {"predicate": "gradable", "equals": "no"},
                },
                {
                    "kind": "implication",
                    "if": {"predicate": "gradable", "equals": "no"},
                    "then": {"predicate": "gradable", "equals": "yes"},
                },
            ],
        }
    )
    changed = replace(
        problem, ontology=problem.ontology.model_copy(update={"feasibility": program})
    )
    observed: dict[str, str] = {}
    for solver in SolverKind:
        try:
            observed[solver.value] = compile_problem(changed, solver).status.value
        except Exception as exc:
            observed[solver.value] = type(exc).__name__
    safe_status = "UNSAT_EVIDENCE_LANGUAGE"
    return {
        "defect_observed": any(value != safe_status for value in observed.values()),
        "expected": safe_status,
        "actual": observed,
    }


def _partial_derivations(problem: Any) -> dict[str, Any]:
    parameters = list(inspect.signature(evaluate_guideline).parameters)
    result = evaluate_guideline(
        problem.guidelines[1],
        EvidenceState(values={"ma_presence": "present"}),
        problem.ontology,
    )
    return {
        "defect_observed": "derivations" not in parameters,
        "expected_parameter": "DecisionContext or derivations",
        "actual_parameters": parameters,
        "actions_without_derivations": [item.values for item in result.actions],
    }


def _typed_identity(problem: Any) -> dict[str, Any]:
    source = problem.ontology.predicates[0].model_copy(
        update={"id": "source", "value_type": "BOOLEAN", "allowed_values": [False, True]}
    )
    target = problem.ontology.predicates[0].model_copy(
        update={"id": "target", "value_type": "INTEGER", "allowed_values": [0, 1]}
    )
    program = FeasibilityProgram.model_validate(
        {
            "schema_version": "1.0",
            "constraints": [
                {
                    "kind": "derived_equality",
                    "source_predicate": "source",
                    "target_predicate": "target",
                }
            ],
        }
    )
    ontology = problem.ontology.model_copy(
        update={"predicates": [source, target], "feasibility": program}
    )
    try:
        validate_ontology(ontology)
    except OntologyValidationError as exc:
        return {"defect_observed": False, "actual": type(exc).__name__, "message": str(exc)}
    return {"defect_observed": True, "actual": "accepted typed-incompatible identity"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_root", type=Path)
    args = parser.parse_args()
    baseline_root = args.baseline_root.resolve()
    project_path = baseline_root / "examples" / "synthetic" / "minimal_dr" / "project.yaml"
    try:
        problem = load_compiler_problem(project_path)
        checks: list[tuple[str, Callable[[Any], dict[str, Any]]]] = [
            ("greedy_prerequisite_closure", _greedy_prerequisite),
            ("finite_feasibility_conflict", _finite_feasibility),
            ("empty_evidence_language", _empty_language),
            ("partial_evaluation_derivations", _partial_derivations),
            ("typed_identity_equality", _typed_identity),
        ]
        results = {name: check(problem) for name, check in checks}
    except Exception as exc:
        print(json.dumps({"probe_error": type(exc).__name__, "message": str(exc)}, indent=2))
        return 2
    all_reproduced = all(item["defect_observed"] for item in results.values())
    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "baseline_commit": BASELINE_COMMIT,
                "all_expected_defects_reproduced": all_reproduced,
                "checks": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if all_reproduced else 2


if __name__ == "__main__":
    sys.exit(main())
