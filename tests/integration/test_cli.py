from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

import g2lc.cli as cli
from g2lc.cli import app

runner = CliRunner()


def test_cli_ontology_validation() -> None:
    result = runner.invoke(
        app,
        ["ontology", "validate", "examples/synthetic/minimal_dr/ontology.yaml", "--json"],
    )
    assert result.exit_code == 0
    assert '"valid": true' in result.stdout


def test_cli_compile_and_verify() -> None:
    compile_result = runner.invoke(
        app,
        ["synthetic", "run", "--fixture", "minimal_dr", "--json"],
    )
    assert compile_result.exit_code == 0
    verify_result = runner.invoke(
        app,
        [
            "certificate",
            "verify",
            "artifacts/synthetic/minimal_dr/certificate.json",
            "--json",
        ],
    )
    assert verify_result.exit_code == 0
    assert '"valid": true' in verify_result.stdout


def test_cli_invalid_fixture_is_nonzero() -> None:
    result = runner.invoke(app, ["synthetic", "run", "--fixture", "not_a_fixture"])
    assert result.exit_code == 2


def test_cli_unknown_evidence_reports_possible_actions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    state = tmp_path / "state.yaml"
    state.write_text("gradable: 'yes'\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "guideline",
            "evaluate",
            "--guideline",
            "examples/synthetic/minimal_dr/guidelines.yaml",
            "--guideline-id",
            "synthetic_guideline_one",
            "--state",
            str(state),
            "--ontology",
            "examples/synthetic/minimal_dr/ontology.yaml",
            "--derivations",
            "examples/synthetic/minimal_dr/derivations.yaml",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert "ACTION_SET" in result.stdout
    assert all(item in result.stdout for item in ("monitor", "refer", "routine"))


def test_cli_data_adapter_dry_run(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "ddr"
    root.mkdir()
    (root / "inventory.jpg").write_bytes(b"metadata-inventory-test")
    result = runner.invoke(
        app,
        [
            "data",
            "adapt",
            "ddr",
            str(root),
            str(tmp_path / "manifest.parquet"),
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert '"unknown_label_count": 1' in result.stdout


def test_cli_guideline_and_operator_context_validation() -> None:
    guideline = runner.invoke(
        app,
        [
            "guideline",
            "validate",
            "examples/synthetic/minimal_dr/guidelines.yaml",
            "--ontology",
            "examples/synthetic/minimal_dr/ontology.yaml",
            "--derivations",
            "examples/synthetic/minimal_dr/derivations.yaml",
            "--json",
        ],
    )
    operator = runner.invoke(
        app,
        [
            "operator",
            "validate",
            "examples/synthetic/minimal_dr/operators.yaml",
            "--ontology",
            "examples/synthetic/minimal_dr/ontology.yaml",
            "--derivations",
            "examples/synthetic/minimal_dr/derivations.yaml",
            "--json",
        ],
    )

    assert guideline.exit_code == 0
    assert '"guidelines": 2' in guideline.stdout
    assert operator.exit_code == 0
    assert '"operators": 7' in operator.stdout


def test_cli_context_files_must_be_paired() -> None:
    guideline = runner.invoke(
        app,
        [
            "guideline",
            "validate",
            "examples/synthetic/minimal_dr/guidelines.yaml",
            "--ontology",
            "examples/synthetic/minimal_dr/ontology.yaml",
        ],
    )
    operator = runner.invoke(
        app,
        [
            "operator",
            "validate",
            "examples/synthetic/minimal_dr/operators.yaml",
            "--derivations",
            "examples/synthetic/minimal_dr/derivations.yaml",
        ],
    )

    assert guideline.exit_code == 2
    assert "provided together" in guideline.stderr
    assert operator.exit_code == 2
    assert "provided together" in operator.stderr


def test_cli_audit_and_metadata_wrappers_record_results(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    split = SimpleNamespace(dataset_id="synthetic", maples_test_lock=True)
    monkeypatch.setattr(cli, "generate_stage1_5_gate", lambda output: {"stage": "1.5"})
    monkeypatch.setattr(
        cli,
        "generate_stage1_6_gate",
        lambda output, required: {"stage": "1.6", "required": required},
    )
    monkeypatch.setattr(cli, "audit_manifest", lambda path: {"rows": 0})
    monkeypatch.setattr(cli, "exact_duplicate_groups", lambda path: [{"digest": "abc"}])
    monkeypatch.setattr(
        cli,
        "write_split_lock",
        lambda path: (split, "digest", tmp_path / "split.lock.json"),
    )

    stage1_5 = runner.invoke(app, ["audit", "stage1-5", "--output", str(tmp_path / "a")])
    stage1_6 = runner.invoke(
        app,
        [
            "audit",
            "stage1-6",
            "--required-pythons",
            "3.11,3.12",
            "--output",
            str(tmp_path / "b"),
            "--json",
        ],
    )
    data_audit = runner.invoke(app, ["data", "audit", str(source), "--json"])
    dedup = runner.invoke(app, ["data", "dedup", str(source), "--json"])
    lock = runner.invoke(app, ["data", "lock-split", str(source), "--json"])

    assert stage1_5.exit_code == 0
    assert stage1_6.exit_code == 0
    assert '"required": ["3.11", "3.12"]' in stage1_6.stdout
    assert data_audit.exit_code == 0
    assert '"rows": 0' in data_audit.stdout
    assert dedup.exit_code == 0
    assert '"digest": "abc"' in dedup.stdout
    assert lock.exit_code == 0
    assert '"maples_test_lock": true' in lock.stdout


def test_cli_status_reads_tracked_status() -> None:
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Project Status" in result.stdout
