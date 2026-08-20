"""Stage-1.6 semantic problem generation and cross-path differential checks."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
import z3

from g2lc.audit.stage1_5 import _coverage_totals
from g2lc.certificates.writer import build_certificate, write_certificate
from g2lc.compiler.counterexample import (
    _derivation_constraints_z3,
    _domain_index,
    _feasibility_constraints_z3,
    _guideline_action_z3,
    find_counterexample,
    solve_counterexample_separation,
)
from g2lc.compiler.exact import brute_force_optimum, solve_exact
from g2lc.compiler.greedy import solve_greedy
from g2lc.compiler.problem import (
    build_finite_problem,
    enumerate_states,
    load_compiler_problem,
)
from g2lc.compiler.result import CompilerStatus, SolverStatus
from g2lc.guidelines.evaluator import action_signature, evaluate_guideline
from g2lc.types import scalar_key
from g2lc.utils.io import canonical_json, sha256_file
from g2lc_verifier import verify_certificate

ROOT = Path(__file__).resolve().parents[3]
REGRESSION_ROOT = ROOT / "tests" / "fixtures" / "regressions" / "generated"


def _provenance(seed: int) -> dict[str, str]:
    return {
        "source": f"Stage-1.6 generated semantic seed {seed}",
        "version": "1.0.0-synthetic",
        "review_status": "SYNTHETIC",
    }


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def generate_semantic_problem(seed: int, directory: Path) -> Path:
    """Write one bounded, varied, explicitly synthetic semantic problem."""

    directory.mkdir(parents=True, exist_ok=True)
    predicate_count = 2 + seed % 5
    predicate_ids = [f"p{index}" for index in range(predicate_count)]
    provenance = _provenance(seed)
    predicates = [
        {
            "id": predicate_id,
            "name": f"Synthetic predicate {predicate_id}",
            "description": "Generated only for cross-path semantic differential testing.",
            "value_type": "BOOLEAN",
            "allowed_values": [False, True],
            "modalities": ["CFP"],
            "observability": "IMAGE_OBSERVABLE",
            "recommended_operators": [f"observe_{predicate_id}"],
            "provenance": provenance,
        }
        for predicate_id in predicate_ids
    ]
    constraints: list[dict[str, Any]] = []
    if seed % 3 == 0:
        constraints.append(
            {
                "kind": "implication",
                "if": {"predicate": predicate_ids[0], "equals": True},
                "then": {"predicate": predicate_ids[-1], "equals": True},
            }
        )
    if predicate_count >= 3 and seed % 5 == 0:
        constraints.append(
            {
                "kind": "mutual_exclusion",
                "conditions": [
                    {"predicate": predicate_ids[1], "equals": True},
                    {"predicate": predicate_ids[2], "equals": True},
                ],
            }
        )
    derivation_rules: list[dict[str, Any]] = []
    if seed % 4 == 0:
        derivation_rules.append(
            {
                "id": "derive_p1_from_p0",
                "input_predicates": [predicate_ids[0]],
                "output_predicates": [predicate_ids[1]],
                "value_mapping": {"bool:false": False, "bool:true": True},
                "provenance": provenance,
            }
        )
    guideline_count = 1 + seed % 3
    guidelines = []
    for guideline_index in range(guideline_count):
        predicate_id = predicate_ids[(seed + guideline_index) % predicate_count]
        guidelines.append(
            {
                "id": f"generated_guideline_{guideline_index}",
                "version": "1.0.0-synthetic",
                "effective_date": "not-clinical",
                "modality_scope": ["CFP"],
                "action_schema": ["decision"],
                "provenance": provenance,
                "rules": [
                    {
                        "id": "positive",
                        "priority": 10 + guideline_index,
                        "when": {"eq": [predicate_id, True]},
                        "then": {"decision": f"positive_{guideline_index}"},
                        "provenance": provenance,
                    }
                ],
                "default_action": {"decision": f"negative_{guideline_index}"},
            }
        )
    operators = []
    for index, predicate_id in enumerate(predicate_ids):
        required = ["observe_p0"] if index > 0 and (seed + index) % 3 == 0 else []
        operators.append(
            {
                "id": f"observe_{predicate_id}",
                "name": f"Observe {predicate_id}",
                "output_predicates": [predicate_id],
                "granularity": "PRESENCE",
                "modalities": ["CFP"],
                "cost": f"{1 + (seed + index) % 4}.{(seed * 7 + index) % 10}",
                "instability": f"0.{(seed + index) % 4}",
                "required_operator_ids": required,
                "provenance": provenance,
            }
        )
    _write_yaml(
        directory / "ontology.yaml",
        {
            "schema_version": "1.0",
            "ontology_id": f"generated_{seed}",
            "version": "1.0.0-synthetic",
            "description": "Generated bounded semantic differential fixture.",
            "provenance": provenance,
            "predicates": predicates,
            "feasibility": {"schema_version": "1.0", "constraints": constraints},
        },
    )
    _write_yaml(
        directory / "guidelines.yaml",
        {"schema_version": "1.0", "synthetic": True, "guidelines": guidelines},
    )
    _write_yaml(
        directory / "operators.yaml",
        {
            "schema_version": "1.0",
            "catalogue_id": f"generated_{seed}",
            "version": "1.0.0-synthetic",
            "synthetic": True,
            "provenance": provenance,
            "operators": operators,
        },
    )
    _write_yaml(
        directory / "derivations.yaml",
        {
            "schema_version": "1.1",
            "graph_id": f"generated_{seed}",
            "version": "1.0.0-synthetic",
            "provenance": provenance,
            "rules": derivation_rules,
        },
    )
    _write_yaml(
        directory / "project.yaml",
        {
            "schema_version": "1.0",
            "project_id": f"generated_{seed}",
            "ontology": "ontology.yaml",
            "guidelines": ["guidelines.yaml"],
            "operators": "operators.yaml",
            "derivations": "derivations.yaml",
            "target_modalities": ["CFP"],
            "instability_weight": f"0.{seed % 3}",
            "max_states": 128,
            "seed": seed,
            "output": "certificate.json",
        },
    )
    return directory / "project.yaml"


def _z3_semantic_rows(
    problem: Any,
) -> tuple[set[tuple[str, ...]], dict[tuple[str, ...], tuple[int, ...]]]:
    variables = {item.id: z3.Int(f"generated__{item.id}") for item in problem.ontology.predicates}
    indices = _domain_index(problem)
    solver = z3.Solver()
    for predicate in problem.ontology.predicates:
        solver.add(variables[predicate.id] >= 0)
        solver.add(variables[predicate.id] < len(predicate.allowed_values))
    solver.add(*_feasibility_constraints_z3(variables, problem, indices))
    solver.add(*_derivation_constraints_z3(variables, problem, indices))
    ordered = sorted(problem.ontology.predicates, key=lambda item: item.id)
    action_expressions = [
        _guideline_action_z3(item, variables, problem, indices) for item in problem.guidelines
    ]
    states: set[tuple[str, ...]] = set()
    actions: dict[tuple[str, ...], tuple[int, ...]] = {}
    while solver.check() == z3.sat:
        model = solver.model()
        row = [model.eval(variables[item.id], model_completion=True).as_long() for item in ordered]
        state_key = tuple(
            scalar_key(item.allowed_values[index]) for item, index in zip(ordered, row, strict=True)
        )
        states.add(state_key)
        actions[state_key] = tuple(
            model.eval(expression, model_completion=True).as_long()
            for expression in action_expressions
        )
        solver.add(
            z3.Or(*[variables[item.id] != index for item, index in zip(ordered, row, strict=True)])
        )
    return states, actions


def _check_semantic_case(seed: int, directory: Path) -> dict[str, Any]:
    project_path = generate_semantic_problem(seed, directory)
    problem = load_compiler_problem(project_path)
    states = enumerate_states(problem)
    ordered = sorted(problem.ontology.predicates, key=lambda item: item.id)
    python_states = {
        tuple(scalar_key(state.values[item.id]) for item in ordered) for state in states
    }
    z3_states, z3_actions = _z3_semantic_rows(problem)
    python_actions = {
        tuple(scalar_key(state.values[item.id]) for item in ordered): tuple(
            action_signature(
                evaluate_guideline(
                    guideline,
                    state,
                    problem.ontology,
                    derivations=problem.graph,
                )
            )
            for guideline in problem.guidelines
        )
        for state in states
    }
    action_partitions_match = all(
        (python_actions[left][guideline_index] == python_actions[right][guideline_index])
        == (z3_actions[left][guideline_index] == z3_actions[right][guideline_index])
        for left in python_states
        for right in python_states
        for guideline_index in range(len(problem.guidelines))
    )
    finite = build_finite_problem(problem)
    reduced = build_finite_problem(problem, relevant_only=True)
    exact = solve_exact(finite)
    reduced_exact = solve_exact(reduced)
    brute = brute_force_optimum(finite)
    separation = solve_counterexample_separation(problem)
    greedy = solve_greedy(finite)
    certificate_path = directory / "certificate.json"
    write_certificate(build_certificate(problem, exact), certificate_path)
    verifier_valid = verify_certificate(certificate_path).valid
    exact_tuple = (exact.selected_operators, exact.total_cost)
    separation_tuple = (separation.selected_operators, separation.total_cost)
    passed = (
        bool(states)
        and python_states == z3_states
        and action_partitions_match
        and brute is not None
        and exact_tuple == brute
        and separation_tuple == brute
        and exact.solver_status is SolverStatus.OPTIMAL
        and separation.solver_status is SolverStatus.OPTIMAL
        and exact_tuple == (reduced_exact.selected_operators, reduced_exact.total_cost)
        and greedy.status is CompilerStatus.EXECUTABLE
        and find_counterexample(problem, greedy.selected_operators) is None
        and verifier_valid
    )
    return {
        "seed": seed,
        "passed": passed,
        "predicate_count": len(problem.ontology.predicates),
        "guideline_count": len(problem.guidelines),
        "feasibility_constraint_count": len(problem.ontology.feasibility.constraints),
        "derivation_rule_count": len(problem.graph.rules),
        "prerequisite_edge_count": sum(
            len(item.required_operator_ids) for item in problem.catalogue.operators
        ),
        "state_count": len(states),
        "relevant_state_count": len(reduced.states),
        "exact": [exact.selected_operators, str(exact.total_cost)],
        "bruteforce": None if brute is None else [brute[0], str(brute[1])],
        "separation": [separation.selected_operators, str(separation.total_cost)],
        "greedy_valid": find_counterexample(problem, greedy.selected_operators) is None,
        "independent_verifier": verifier_valid,
        "action_partitions_match": action_partitions_match,
    }


def run_semantic_generated_matrix(case_count: int = 200) -> dict[str, Any]:
    """Run deterministic semantic, not merely cost, differential problems."""

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="g2lc-stage1-6-") as temporary:
        base = Path(temporary)
        for seed in range(case_count):
            case_directory = base / f"seed_{seed:04d}"
            try:
                result = _check_semantic_case(seed, case_directory)
            except Exception as exc:  # the gate records and preserves exact failing seeds
                result = {"seed": seed, "passed": False, "error": repr(exc)}
            results.append(result)
            if not result["passed"]:
                failures.append(result)
                destination = REGRESSION_ROOT / f"seed_{seed:04d}"
                if case_directory.exists():
                    shutil.copytree(case_directory, destination, dirs_exist_ok=True)
                    (destination / "failure.json").write_text(
                        canonical_json(result) + "\n", encoding="utf-8"
                    )
    return {
        "passed": not failures,
        "semantic_generated_cases": case_count,
        "semantic_generated_failures": len(failures),
        "duration_seconds": round(time.perf_counter() - started, 4),
        "failures": failures,
        "cases": results,
        "reproduction_command": (
            "uv run g2lc synthetic matrix --random-seeds 20 "
            f"--semantic-generated-cases {case_count}"
        ),
    }


def write_semantic_matrix(path: Path, case_count: int = 200) -> dict[str, Any]:
    payload = run_semantic_generated_matrix(case_count)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _git_value(*arguments: str) -> str | None:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _junit_summary(path: Path) -> tuple[int, int, dict[str, bool]]:
    if not path.is_file():
        return 0, 1, {}
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    outcomes = {
        item.attrib.get("name", "unknown"): not any(
            item.find(kind) is not None for kind in ("failure", "error")
        )
        for item in cases
    }
    failures = sum(not passed for passed in outcomes.values())
    return len(cases), failures, outcomes


def generate_gate(output: str | Path, required_pythons: list[str] | None = None) -> dict[str, Any]:
    """Generate Stage-1.6 evidence without inventing a successful self-audit command."""

    audit = ROOT / "artifacts" / "audit" / "stage1_6"
    environments_root = audit / "environments"
    environment_results: dict[str, Any] = {}
    required = required_pythons or [f"{sys.version_info.major}.{sys.version_info.minor}"]
    for version in required:
        token = f"python_{version.replace('.', '_')}"
        directory = environments_root / token
        command_path = directory / "command_results.json"
        commands = (
            json.loads(command_path.read_text(encoding="utf-8"))
            if command_path.is_file()
            else {"commands": []}
        )
        coverage_path = directory / "coverage.json"
        coverage = (
            json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.is_file() else {}
        )
        line, branch = _coverage_totals(coverage)
        core_line, core_branch = _coverage_totals(
            coverage,
            [
                "src/g2lc/guidelines/",
                "src/g2lc/compiler/",
                "src/g2lc/certificates/",
                "src/g2lc_verifier/",
            ],
        )
        test_count, failed_tests, test_outcomes = _junit_summary(directory / "junit.xml")
        exit_codes = {item["command"]: item["exit_code"] for item in commands["commands"]}
        command_pass = bool(exit_codes) and all(value == 0 for value in exit_codes.values())
        coverage_pass = (
            line >= 92.4229 and branch >= 85.6073 and core_line >= 95 and core_branch >= 90
        )
        environment_results[version] = {
            "python_version": commands.get("python_version"),
            "commands": commands.get("commands", []),
            "command_pass": command_pass,
            "test_count": test_count,
            "failed_test_count": failed_tests,
            "line_coverage": line,
            "branch_coverage": branch,
            "core_line_coverage": core_line,
            "core_branch_coverage": core_branch,
            "coverage_no_regression": coverage_pass,
            "focused_semantic_tests": {
                name: passed
                for name, passed in test_outcomes.items()
                if any(
                    marker in name
                    for marker in (
                        "greedy",
                        "conflict_validation",
                        "empty_evidence",
                        "partial_evaluation",
                        "relevant_state_projection",
                        "generated_feasibility_hash",
                    )
                )
            },
            "passed": command_pass and failed_tests == 0 and test_count > 0 and coverage_pass,
        }
    matrix_path = audit / "solver_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8")) if matrix_path.is_file() else {}
    semantic = matrix.get("semantic_generated_results", {})
    matrix_pass = all(
        bool(matrix.get(item, {}).get("passed"))
        for item in (
            "finite_vs_bruteforce_results",
            "finite_vs_z3_results",
            "exact_vs_separation_results",
            "verifier_independence_check",
            "tamper_matrix_results",
        )
    ) and bool(semantic.get("passed"))
    commit = _git_value("rev-parse", "HEAD")
    verification_files = sorted(
        (ROOT / "artifacts" / "review").glob(f"G2LC_DR_STAGE1_6_REVIEW_{commit}_verification.json")
    )
    bundle_verification = (
        json.loads(verification_files[-1].read_text(encoding="utf-8"))
        if verification_files
        else {"passed": False, "reason": "review bundle not generated yet"}
    )
    prechange_path = audit / "prechange.json"
    regression_path = audit / "regressions_before.json"
    prechange = (
        json.loads(prechange_path.read_text(encoding="utf-8")) if prechange_path.is_file() else None
    )
    regressions_before = (
        json.loads(regression_path.read_text(encoding="utf-8"))
        if regression_path.is_file()
        else None
    )
    final_status = (
        "PASS"
        if all(environment_results.get(item, {}).get("passed") for item in required)
        and matrix_pass
        and regressions_before is not None
        and bundle_verification.get("passed")
        else "FAIL"
    )
    payload = {
        "schema_version": "1.0",
        "stage": "1.6",
        "semantic_contract": "action-only-decision-sufficiency-v1.1",
        "starting_commit": "ec3250d7e3dba0379c3b5205949c23e4f4ee5d59",
        "git_commit": commit,
        "git_branch": _git_value("branch", "--show-current"),
        "dirty_tracked_worktree": bool(_git_value("status", "--short", "--untracked-files=no")),
        "generator_python_version": platform.python_version(),
        "dependency_lock_hash": sha256_file(ROOT / "uv.lock"),
        "prechange_snapshot": prechange,
        "failing_regressions_before_fix": regressions_before,
        "required_python_versions": required,
        "environment_results": environment_results,
        "solver_equivalence_results": {
            "cost_randomized_cases": matrix.get("randomized_instance_count"),
            "finite_vs_bruteforce": matrix.get("finite_vs_bruteforce_results"),
            "finite_vs_z3": matrix.get("finite_vs_z3_results"),
            "exact_vs_separation": matrix.get("exact_vs_separation_results"),
            "semantic_generated_cases": semantic.get("semantic_generated_cases"),
            "semantic_generated_failures": semantic.get("semantic_generated_failures"),
            "passed": matrix_pass,
        },
        "tamper_results": matrix.get("tamper_matrix_results"),
        "verifier_independence": matrix.get("verifier_independence_check"),
        "review_bundle_verification": bundle_verification,
        "gate_generation": {
            "method": "direct evidence aggregation after recorded subprocesses",
            "self_assumed_exit_code": False,
        },
        "known_remaining_defects": [],
        "final_status": final_status,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return payload
