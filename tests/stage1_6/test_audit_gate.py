from __future__ import annotations

import json
import sys
from pathlib import Path

import g2lc.audit.stage1_6 as audit
from g2lc.audit.stage1_6 import generate_gate, run_semantic_generated_matrix


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_generated_semantic_matrix_varies_and_agrees() -> None:
    result = run_semantic_generated_matrix(12)

    assert result["passed"] is True
    assert result["semantic_generated_cases"] == 12
    assert {item["predicate_count"] for item in result["cases"]} == {2, 3, 4, 5, 6}
    assert any(item["feasibility_constraint_count"] for item in result["cases"])
    assert any(item["derivation_rule_count"] for item in result["cases"])
    assert any(item["prerequisite_edge_count"] for item in result["cases"])


def test_gate_aggregates_only_recorded_evidence(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    environment = (
        tmp_path
        / "artifacts"
        / "audit"
        / "stage1_6"
        / "environments"
        / f"python_{version.replace('.', '_')}"
    )
    _write_json(
        environment / "command_results.json",
        {
            "python_version": version,
            "commands": [{"command": "recorded", "exit_code": 0, "log": "logs/01.log"}],
        },
    )
    _write_json(
        environment / "coverage.json",
        {
            "files": {
                "src/g2lc/compiler/example.py": {
                    "summary": {
                        "covered_lines": 100,
                        "num_statements": 100,
                        "covered_branches": 100,
                        "num_branches": 100,
                    }
                }
            }
        },
    )
    (environment / "junit.xml").write_text(
        '<testsuite><testcase name="test_greedy_recorded"/></testsuite>', encoding="utf-8"
    )
    audit_root = tmp_path / "artifacts" / "audit" / "stage1_6"
    matrix = {
        "randomized_instance_count": 20,
        "finite_vs_bruteforce_results": {"passed": True},
        "finite_vs_z3_results": {"passed": True},
        "exact_vs_separation_results": {"passed": True},
        "verifier_independence_check": {"passed": True},
        "tamper_matrix_results": {"passed": True},
        "semantic_generated_results": {
            "passed": True,
            "semantic_generated_cases": 200,
            "semantic_generated_failures": 0,
        },
    }
    _write_json(audit_root / "solver_matrix.json", matrix)
    _write_json(audit_root / "prechange.json", {"baseline": "recorded"})
    _write_json(audit_root / "regressions_before.json", {"failed": 7})
    (tmp_path / "uv.lock").write_text("locked", encoding="utf-8")
    commit = "a" * 40
    _write_json(
        tmp_path / "artifacts" / "review" / f"G2LC_DR_STAGE1_6_REVIEW_{commit}_verification.json",
        {"passed": True},
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(
        audit,
        "_git_value",
        lambda *arguments: "" if arguments[0] == "status" else commit,
    )

    result = generate_gate(audit_root / "gate.json", [version])

    assert result["final_status"] == "PASS"
    assert result["gate_generation"]["self_assumed_exit_code"] is False
