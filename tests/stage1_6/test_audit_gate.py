from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

import g2lc.audit.stage1_6 as audit
from g2lc.audit.stage1_6 import (
    generate_gate,
    generate_semantic_problem,
    run_semantic_generated_matrix,
    write_semantic_matrix,
)


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


def test_generated_problem_varies_every_declared_semantic_axis(tmp_path: Path) -> None:
    value_types: set[str] = set()
    constraint_kinds: set[str] = set()
    modalities: set[str] = set()
    availabilities: set[str] = set()
    has_operator_mapping = False
    has_multi_rule_guideline = False
    has_transitive_prerequisites = False

    for seed in range(60):
        directory = tmp_path / f"seed_{seed:04d}"
        generate_semantic_problem(seed, directory)
        ontology = yaml.safe_load((directory / "ontology.yaml").read_text(encoding="utf-8"))
        guidelines = yaml.safe_load((directory / "guidelines.yaml").read_text(encoding="utf-8"))
        operators = yaml.safe_load((directory / "operators.yaml").read_text(encoding="utf-8"))
        value_types.update(item["value_type"] for item in ontology["predicates"])
        constraint_kinds.update(item["kind"] for item in ontology["feasibility"]["constraints"])
        for operator in operators["operators"]:
            modalities.update(operator["modalities"])
            availabilities.add(operator.get("availability", "AVAILABLE"))
            has_operator_mapping = has_operator_mapping or bool(operator.get("value_mappings"))
        has_multi_rule_guideline = has_multi_rule_guideline or any(
            len(item["rules"]) > 1 for item in guidelines["guidelines"]
        )
        required = {
            item["id"]: item.get("required_operator_ids", []) for item in operators["operators"]
        }
        has_transitive_prerequisites = has_transitive_prerequisites or any(
            any(required.get(parent) for parent in parents) for parents in required.values()
        )

    assert value_types == {"BOOLEAN", "CATEGORICAL", "INTEGER"}
    assert constraint_kinds == {
        "implication",
        "mutual_exclusion",
        "conditional_allowed",
        "exactly_one",
        "at_most_one",
        "derived_equality",
        "parent_child",
    }
    assert modalities == {"CFP", "UWF"}
    assert availabilities == {"AVAILABLE", "UNAVAILABLE"}
    assert has_operator_mapping
    assert has_multi_rule_guideline
    assert has_transitive_prerequisites


def test_stage1_6_coverage_thresholds_match_authoritative_prompt() -> None:
    assert audit.COVERAGE_THRESHOLDS == {
        "whole_line": 92.0,
        "whole_branch": 86.0,
        "core_line": 96.0,
        "core_branch": 91.0,
    }


def test_semantic_matrix_writer_records_reproduction(tmp_path: Path) -> None:
    path = tmp_path / "matrix.json"

    result = write_semantic_matrix(path, 1)

    assert result["passed"] is True
    assert json.loads(path.read_text(encoding="utf-8"))["semantic_generated_cases"] == 1


def test_generated_failure_is_persisted_with_portable_path(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    regression_root = tmp_path / "regressions"

    def fail(seed: int, directory: Path) -> dict[str, object]:
        directory.mkdir(parents=True)
        (directory / "project.yaml").write_text("schema_version: '1.0'\n", encoding="utf-8")
        raise RuntimeError(f"{directory / 'project.yaml'}: synthetic failure")

    monkeypatch.setattr(audit, "_check_semantic_case", fail)
    monkeypatch.setattr(audit, "REGRESSION_ROOT", regression_root)

    result = audit.run_semantic_generated_matrix(1)

    assert result["passed"] is False
    assert "<generated-root>" in result["failures"][0]["error"]
    assert str(tmp_path) not in result["failures"][0]["error"]
    persisted = json.loads(
        (regression_root / "seed_0000" / "failure.json").read_text(encoding="utf-8")
    )
    assert persisted == result["failures"][0]


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
            "commands": [
                {
                    "command": marker,
                    "exit_code": 0,
                    "duration_seconds": 0.1,
                    "log": f"logs/{index:02d}.log",
                }
                for index, marker in enumerate(audit.MANDATORY_COMMAND_MARKERS, start=1)
            ],
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
    _write_json(
        environment / "package_audit.json",
        {
            "passed": True,
            "archives": [
                {"kind": "wheel", "members": ["g2lc/__init__.py"]},
                {"kind": "sdist", "members": ["g2lc_dr-0.1.0/pyproject.toml"]},
            ],
            "clean_install_smoke": [{"passed": True}, {"passed": True}],
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
        tmp_path
        / "artifacts"
        / "review"
        / f"G2LC_DR_STAGE1_6_1_REVIEW_{commit[:12]}_verification.json",
        {
            "passed": True,
            "embedded_commit": commit,
            "recursive_checksum_externalized": True,
        },
    )
    archive = tmp_path / "artifacts" / "review" / f"G2LC_DR_STAGE1_6_1_REVIEW_{commit[:12]}.zip"
    archive.write_bytes(b"verified-review-bundle")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (
        tmp_path / "artifacts" / "review" / f"G2LC_DR_STAGE1_6_1_REVIEW_{commit[:12]}.sha256"
    ).write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    _write_json(
        tmp_path
        / "artifacts"
        / "review"
        / f"G2LC_DR_STAGE1_6_1_REVIEW_{commit[:12]}_final_metadata.json",
        {"archive": {"sha256": digest}},
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)

    def fake_git(*arguments: str) -> str:
        if arguments[0] == "status":
            return ""
        if arguments[:2] == ("rev-parse", "--short=12"):
            return commit[:12]
        if arguments[0] == "branch":
            return "codex/stage1-6-cross-path-hardening"
        return commit

    monkeypatch.setattr(
        audit,
        "_git_value",
        fake_git,
    )

    result = generate_gate(audit_root / "gate.json", [version])

    assert result["final_status"] == "PASS"
    assert result["stage"] == "1.6.1"
    assert result["gate_generation"]["self_assumed_exit_code"] is False
    assert result["failure_count"] == 0
    assert result["commands"]

    command_path = environment / "command_results.json"
    recorded = json.loads(command_path.read_text(encoding="utf-8"))
    recorded["commands"].pop()
    _write_json(command_path, recorded)

    failed = generate_gate(audit_root / "gate.json", [version])

    assert failed["final_status"] == "FAIL"
    assert failed["environment_results"][version]["missing_mandatory_commands"]
