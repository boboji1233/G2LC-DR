from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import g2lc.audit.stage1_5 as audit_module
from g2lc.audit.stage1_5 import generate_gate, run_synthetic_matrix

REQUIRED = [
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


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _gate_evidence(directory: Path) -> None:
    logs = directory / "logs"
    logs.mkdir(parents=True)
    commands = []
    for index, command in enumerate(REQUIRED):
        log = logs / f"{index}.log"
        log.write_text("127 passed in 1.0s\n", encoding="utf-8")
        commands.append(
            {"command": command, "exit_code": 0, "log": log.relative_to(directory).as_posix()}
        )
    _write(
        directory / "command_results.json",
        {"uv_version": "uv test", "commands": commands},
    )
    perfect = {
        "summary": {
            "covered_lines": 100,
            "num_statements": 100,
            "covered_branches": 100,
            "num_branches": 100,
        }
    }
    _write(
        directory / "coverage.json",
        {
            "files": {
                "src/g2lc/guidelines/example.py": perfect,
                "src/g2lc/compiler/example.py": perfect,
                "src/g2lc/certificates/example.py": perfect,
                "src/g2lc_verifier/example.py": perfect,
                "src/g2lc/data/example.py": perfect,
            }
        },
    )
    _write(
        directory / "solver_matrix.json",
        {
            "finite_vs_bruteforce_results": {"passed": True},
            "finite_vs_z3_results": {"passed": True},
            "exact_vs_separation_results": {"passed": True},
            "verifier_independence_check": {"passed": True},
            "tamper_matrix_results": {"passed": True},
        },
    )


def test_production_synthetic_matrix_runs_all_checks() -> None:
    result = run_synthetic_matrix(random_seeds=2)
    assert result["randomized_instance_count"] == 2
    assert result["finite_vs_z3_results"] == {
        "passed": True,
        "scheme_count": 66,
        "mismatches": [],
    }
    assert result["finite_vs_bruteforce_results"]["passed"] is True
    assert result["exact_vs_separation_results"]["passed"] is True
    assert result["verifier_independence_check"]["passed"] is True
    assert result["tamper_matrix_results"]["rejected_count"] == 54


def test_required_fixture_manifest_is_complete() -> None:
    path = Path("examples/synthetic/stage1_5/fixture_matrix.yaml")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    fixtures = payload["fixtures"]
    expected = {
        "priority_unknown_blocks_lower_action",
        "same_action_different_clause",
        "default_same_action_as_rule",
        "typed_bool_int_collision",
        "infeasible_state_false_counterexample",
        "deterministic_derivation_mapping",
        "derivation_inconsistent_state_rejected",
        "operator_prerequisite_chain",
        "unavailable_prerequisite_repair",
        "modality_mismatch",
        "submill_cost_ordering",
        "equal_cost_lexicographic_tie",
        "incremental_repair_differs_from_total_reopt",
        "same_priority_conflict_large_space",
        "rehashed_certificate_tamper_matrix",
        "symbolic_certificate_does_not_enumerate",
        "verifier_import_boundary",
    }
    assert payload["synthetic"] is True
    assert {item["id"] for item in fixtures} == expected
    for item in fixtures:
        assert item["provenance"] == "SYNTHETIC"
        assert item["expected_semantic_outcome"]
        assert item["expected_exact_objective"] is not None
        assert item["expected_certificate_type"]
        test_path, test_name = item["focused_test"].split("::", maxsplit=1)
        assert Path(test_path).is_file()
        assert f"def {test_name}(" in Path(test_path).read_text(encoding="utf-8")


def test_gate_generation_pass_and_internal_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = tmp_path / "audit"
    _gate_evidence(audit)
    monkeypatch.setattr(audit_module, "AUDIT_DIR", audit)
    passed = generate_gate(tmp_path / "pass.json")
    assert passed["final_status"] == "PASS"
    assert passed["test_count"] == 127
    assert passed["line_coverage"] == 100
    assert passed["branch_coverage"] == 100
    assert passed["core_line_coverage"] == 100
    assert passed["core_branch_coverage"] == 100
    assert "git_commit" in passed

    commands = json.loads((audit / "command_results.json").read_text(encoding="utf-8"))
    commands["commands"][0]["exit_code"] = 1
    _write(audit / "command_results.json", commands)
    failed = generate_gate(tmp_path / "fail.json")
    assert failed["final_status"] == "FAIL"
