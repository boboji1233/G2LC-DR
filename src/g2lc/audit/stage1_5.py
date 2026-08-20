"""Reproducible Stage-1.5 differential, tamper, and gate evidence."""

from __future__ import annotations

import copy
import itertools
import json
import platform
import random
import re
import shutil
import subprocess
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from g2lc.certificates.writer import build_certificate, write_certificate
from g2lc.compiler.api import compile_problem
from g2lc.compiler.counterexample import find_counterexample, solve_counterexample_separation
from g2lc.compiler.exact import brute_force_optimum, solve_exact
from g2lc.compiler.problem import build_finite_problem, load_compiler_problem
from g2lc.compiler.result import SolverKind, SolverStatus
from g2lc.errors import CertificateVerificationError
from g2lc.utils.io import canonical_json, sha256_file, sha256_json
from g2lc_verifier import verify_certificate

ROOT = Path(__file__).resolve().parents[3]
AUDIT_DIR = ROOT / "artifacts" / "audit" / "stage1_5"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _rehash(data: dict[str, Any]) -> None:
    body = dict(data)
    body.pop("certificate_hash")
    body.pop("content_checksum")
    digest = sha256_json(body)
    data["certificate_hash"] = digest
    data["content_checksum"] = digest


def _tamper(data: dict[str, Any], field: str) -> None:
    if field == "proof_scope":
        data[field] = "BOUNDED"
    elif field == "assumptions":
        data[field] = []
    elif field in {
        "ontology_hash",
        "operator_catalogue_hash",
        "derivation_graph_hash",
        "feasibility_hash",
        "decision_program_hash",
    }:
        data[field] = "0" * 64
    elif field == "guideline_hashes":
        key = next(iter(data[field]))
        data[field][key] = "0" * 64
    elif field in {
        "selected_operators",
        "derived_predicates",
        "guidelines_covered",
        "clauses_covered",
    }:
        data[field] = []
    elif field in {"operator_closure", "action_programs"}:
        data[field] = {}
    elif field == "action_distinction_count":
        data[field] = 0 if data[field] is None else data[field] + 1
    elif field == "total_cost":
        data[field] = "999"
    elif field == "objective_tuple":
        data[field][0] = "999"
    elif field == "optimality":
        data[field]["lexical_proven"] = False
    elif field == "solver_status":
        data[field] = "FEASIBLE"
    elif field == "verification":
        finite_count = data[field]["finite_state_count"]
        data[field]["finite_state_count"] = 0 if finite_count is None else finite_count + 1
    elif field == "proof_method":
        data["verification"]["method"] = "tampered-method"
    elif field == "action_programs":
        data[field] = {}
    elif field == "source_hashes":
        data[field][0]["sha256"] = "0" * 64
    elif field in {"uncovered_counterexamples", "missing_predicates", "minimal_additions"}:
        data[field] = []
    elif field == "minimum_repair_cost":
        data[field] = "999"
    elif field == "findings":
        data[field] = []
    elif field == "counterexample_state":
        witness = data["uncovered_counterexamples"][0]
        witness["left"] = copy.deepcopy(witness["right"])
    elif field == "oos_reason":
        data["findings"][0]["reason"] = "tampered reason"
    elif field == "oos_required_modalities":
        data["findings"][0]["required_modalities"] = []
    elif field == "oos_source_clauses":
        data["findings"][0]["source_clauses"] = []
    else:
        raise ValueError(field)


def _verifier_independence() -> dict[str, Any]:
    package = ROOT / "src" / "g2lc_verifier"
    files = sorted(package.rglob("*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    forbidden = [
        item
        for item in ("g2lc.compiler", "g2lc.certificates.writer", "g2lc.compiler.result")
        if item in source
    ]
    return {
        "passed": package.is_dir() and bool(files) and not forbidden,
        "files_checked": len(files),
        "forbidden_imports": forbidden,
    }


def _tamper_matrix(problem_path: Path) -> dict[str, Any]:
    path = AUDIT_DIR / "tamper_certificate.json"
    cases = [
        (
            "EXECUTABLE",
            problem_path,
            SolverKind.EXACT,
            [
                "proof_scope",
                "assumptions",
                "ontology_hash",
                "guideline_hashes",
                "operator_catalogue_hash",
                "derivation_graph_hash",
                "feasibility_hash",
                "decision_program_hash",
                "selected_operators",
                "derived_predicates",
                "operator_closure",
                "action_distinction_count",
                "total_cost",
                "objective_tuple",
                "optimality",
                "solver_status",
                "verification",
                "proof_method",
                "action_programs",
                "guidelines_covered",
                "clauses_covered",
                "source_hashes",
            ],
        ),
        (
            "INCOMPLETE",
            ROOT / "examples" / "synthetic" / "missing_evidence" / "project.yaml",
            SolverKind.EXACT,
            [
                "uncovered_counterexamples",
                "missing_predicates",
                "minimal_additions",
                "minimum_repair_cost",
                "counterexample_state",
            ],
        ),
        (
            "OUT_OF_SPEC",
            ROOT / "examples" / "synthetic" / "out_of_spec" / "project.yaml",
            SolverKind.EXACT,
            ["findings", "oos_reason", "oos_required_modalities", "oos_source_clauses"],
        ),
        (
            "EXECUTABLE_SMT_UNIVERSAL",
            problem_path,
            SolverKind.SEPARATION,
            [
                "action_distinction_count",
                "verification",
                "proof_method",
                "total_cost",
                "objective_tuple",
                "optimality",
                "solver_status",
                "action_programs",
                "guidelines_covered",
            ],
        ),
        (
            "INCOMPLETE_SMT_UNIVERSAL",
            ROOT / "examples" / "synthetic" / "missing_evidence" / "project.yaml",
            SolverKind.SEPARATION,
            [
                "uncovered_counterexamples",
                "missing_predicates",
                "minimal_additions",
                "minimum_repair_cost",
                "counterexample_state",
            ],
        ),
    ]
    results: list[dict[str, Any]] = []
    last_original: dict[str, Any] = {}
    for certificate_type, source_path, solver_kind, fields in cases:
        problem = load_compiler_problem(source_path)
        solution = compile_problem(problem, solver_kind)
        certificate = build_certificate(problem, solution)
        write_certificate(certificate, path)
        original = json.loads(path.read_text(encoding="utf-8"))
        last_original = original
        for field in fields:
            changed = copy.deepcopy(original)
            _tamper(changed, field)
            _rehash(changed)
            _write_json(path, changed)
            rejected = False
            reason = ""
            try:
                verify_certificate(path)
            except CertificateVerificationError as exc:
                rejected = True
                reason = str(exc)
            results.append(
                {
                    "certificate_type": certificate_type,
                    "field": field,
                    "rejected": rejected,
                    "reason": reason,
                }
            )
    _write_json(path, last_original)
    return {
        "passed": all(item["rejected"] for item in results),
        "case_count": len(results),
        "rejected_count": sum(bool(item["rejected"]) for item in results),
        "cases": results,
    }


def run_synthetic_matrix(*, random_seeds: int = 20) -> dict[str, Any]:
    """Compare every exact path on deterministic small synthetic instances."""

    problem_path = ROOT / "examples" / "synthetic" / "minimal_dr" / "project.yaml"
    problem = load_compiler_problem(problem_path)
    finite = build_finite_problem(problem)
    operator_ids = [item.id for item in finite.operators]
    operator_map = {item.id: item for item in finite.operators}
    universe = set(range(len(finite.pairs)))
    finite_z3_mismatches: list[dict[str, Any]] = []
    checked_schemes = 0
    for flags in itertools.product((False, True), repeat=len(operator_ids)):
        selected = {item for item, enabled in zip(operator_ids, flags, strict=True) if enabled}
        if any(
            not set(operator_map[item].required_operator_ids).issubset(selected)
            for item in selected
        ):
            continue
        checked_schemes += 1
        covered = set().union(*(finite.coverage[item] for item in selected)) if selected else set()
        finite_executable = covered == universe
        z3_executable = find_counterexample(problem, sorted(selected)) is None
        if finite_executable != z3_executable:
            finite_z3_mismatches.append(
                {
                    "selected_operators": sorted(selected),
                    "finite_executable": finite_executable,
                    "z3_executable": z3_executable,
                }
            )

    seeded: list[dict[str, Any]] = []
    for seed in range(random_seeds):
        randomizer = random.Random(seed)
        operators = [
            item.model_copy(
                update={"cost": Decimal(randomizer.randint(1, 5000)) / Decimal("1000000")}
            )
            for item in problem.catalogue.operators
        ]
        catalogue = problem.catalogue.model_copy(update={"operators": operators})
        instance = replace(problem, catalogue=catalogue)
        instance_finite = build_finite_problem(instance)
        exact = solve_exact(instance_finite)
        brute = brute_force_optimum(instance_finite)
        separation = solve_counterexample_separation(instance)
        expected = (brute[0], str(brute[1])) if brute is not None else (None, None)
        exact_value = (exact.selected_operators, str(exact.total_cost))
        separation_value = (
            separation.selected_operators,
            str(separation.total_cost),
        )
        passed = (
            brute is not None
            and exact_value == expected
            and separation_value == expected
            and exact.solver_status is SolverStatus.OPTIMAL
            and separation.solver_status is SolverStatus.OPTIMAL
        )
        seeded.append(
            {
                "seed": seed,
                "passed": passed,
                "bruteforce": expected,
                "finite_exact": exact_value,
                "separation": separation_value,
            }
        )

    verifier = _verifier_independence()
    tamper = _tamper_matrix(problem_path)
    payload = {
        "schema_version": "1.0",
        "semantic_contract": "action-only-decision-sufficiency-v1.1",
        "randomized_instance_count": random_seeds,
        "finite_vs_bruteforce_results": {
            "passed": all(item["passed"] for item in seeded),
            "cases": seeded,
        },
        "finite_vs_z3_results": {
            "passed": not finite_z3_mismatches,
            "scheme_count": checked_schemes,
            "mismatches": finite_z3_mismatches,
        },
        "exact_vs_separation_results": {
            "passed": all(item["passed"] for item in seeded),
            "cases": seeded,
        },
        "verifier_independence_check": verifier,
        "tamper_matrix_results": tamper,
    }
    _write_json(AUDIT_DIR / "solver_matrix.json", payload)
    return payload


def _coverage_totals(
    coverage: dict[str, Any], paths: list[str] | None = None
) -> tuple[float, float]:
    files = coverage.get("files", {})
    selected = [
        summary["summary"]
        for path, summary in files.items()
        if paths is None or any(fragment in path.replace("\\", "/") for fragment in paths)
    ]
    covered_lines = sum(int(item.get("covered_lines", 0)) for item in selected)
    statements = sum(int(item.get("num_statements", 0)) for item in selected)
    covered_branches = sum(int(item.get("covered_branches", 0)) for item in selected)
    branches = sum(int(item.get("num_branches", 0)) for item in selected)
    line = 100.0 if statements == 0 else 100.0 * covered_lines / statements
    branch = 100.0 if branches == 0 else 100.0 * covered_branches / branches
    return round(line, 4), round(branch, 4)


def _command_text(command_results: dict[str, Any]) -> str:
    return "\n".join(
        (AUDIT_DIR / item["log"]).read_text(encoding="utf-8", errors="replace")
        for item in command_results.get("commands", [])
        if item.get("log") and (AUDIT_DIR / item["log"]).is_file()
    )


def _git_value(arguments: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.returncode, result.stdout.strip()


def generate_gate(output: str | Path) -> dict[str, Any]:
    """Generate the mandatory gate document exclusively from current evidence."""

    command_path = AUDIT_DIR / "command_results.json"
    command_results = (
        json.loads(command_path.read_text(encoding="utf-8"))
        if command_path.is_file()
        else {"commands": []}
    )
    coverage_path = AUDIT_DIR / "coverage.json"
    coverage = (
        json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.is_file() else {}
    )
    line_coverage, branch_coverage = _coverage_totals(coverage)
    core_line, core_branch = _coverage_totals(
        coverage,
        [
            "src/g2lc/guidelines/",
            "src/g2lc/compiler/",
            "src/g2lc/certificates/",
            "src/g2lc_verifier/",
        ],
    )
    matrix_path = AUDIT_DIR / "solver_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8")) if matrix_path.is_file() else {}
    combined_log = _command_text(command_results)
    passed_matches = [int(item) for item in re.findall(r"(\d+) passed", combined_log)]
    failed_matches = [int(item) for item in re.findall(r"(\d+) failed", combined_log)]
    test_count = max(passed_matches, default=0) + max(failed_matches, default=0)
    failed_test_count = max(failed_matches, default=0)

    fixture_hashes = {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in sorted((ROOT / "examples" / "synthetic").rglob("*"))
        if path.is_file()
    }
    head_exit, head = _git_value(["rev-parse", "HEAD"])
    status_exit, status = _git_value(["status", "--short"])
    uv_path = shutil.which("uv")
    if uv_path is None:
        uv_version = command_results.get("uv_version")
    else:
        uv_result = subprocess.run(
            [uv_path, "--version"], cwd=ROOT, text=True, capture_output=True, check=False
        )
        uv_version = (
            uv_result.stdout.strip()
            if uv_result.returncode == 0
            else command_results.get("uv_version")
        )
    commands = [item["command"] for item in command_results.get("commands", [])]
    exit_codes = {
        item["command"]: item["exit_code"] for item in command_results.get("commands", [])
    }
    audit_command = "uv run g2lc audit stage1-5 --output artifacts/audit/stage1_5/gate.json"
    if audit_command not in commands:
        commands.append(audit_command)
        exit_codes[audit_command] = 0
    required_before_audit = [
        "uv sync --locked --all-groups",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src tests",
        "uv run pytest -q --cov=g2lc --cov=g2lc_verifier --cov-branch "
        "--cov-report=term-missing "
        "--cov-report=json:artifacts/audit/stage1_5/coverage.json --cov-fail-under=90",
        "uv build",
        "uv run g2lc synthetic matrix",
    ]
    command_pass = all(exit_codes.get(item) == 0 for item in required_before_audit)
    matrix_pass = all(
        bool(matrix.get(item, {}).get("passed"))
        for item in (
            "finite_vs_bruteforce_results",
            "finite_vs_z3_results",
            "exact_vs_separation_results",
            "verifier_independence_check",
            "tamper_matrix_results",
        )
    )
    coverage_pass = (
        line_coverage >= 90 and branch_coverage >= 85 and core_line >= 95 and core_branch >= 90
    )
    final_status = (
        "PASS"
        if command_pass
        and failed_test_count == 0
        and test_count > 0
        and coverage_pass
        and matrix_pass
        else "FAIL"
    )
    build_exit = exit_codes.get("uv build")
    payload = {
        "git_commit": head if head_exit == 0 else None,
        "dirty_worktree": bool(status) if status_exit == 0 else None,
        "python_version": platform.python_version(),
        "uv_version": uv_version,
        "dependency_lock_hash": sha256_file(ROOT / "uv.lock"),
        "commands": commands,
        "exit_codes": exit_codes,
        "test_count": test_count,
        "failed_test_count": failed_test_count,
        "line_coverage": line_coverage,
        "branch_coverage": branch_coverage,
        "core_line_coverage": core_line,
        "core_branch_coverage": core_branch,
        "fixture_hashes": fixture_hashes,
        "finite_vs_bruteforce_results": matrix.get("finite_vs_bruteforce_results"),
        "finite_vs_z3_results": matrix.get("finite_vs_z3_results"),
        "exact_vs_separation_results": matrix.get("exact_vs_separation_results"),
        "verifier_independence_check": matrix.get("verifier_independence_check"),
        "tamper_matrix_results": matrix.get("tamper_matrix_results"),
        "package_build_result": {
            "passed": build_exit == 0,
            "exit_code": build_exit,
            "artifacts": [
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                }
                for path in sorted((ROOT / "dist").glob("*"))
                if path.is_file()
            ],
        },
        "final_status": final_status,
    }
    _write_json(Path(output), payload)
    return payload
