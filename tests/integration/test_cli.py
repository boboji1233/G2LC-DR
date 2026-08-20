from __future__ import annotations

from typer.testing import CliRunner

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
