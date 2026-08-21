from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from g2lc import cli
from g2lc.cli import app

runner = CliRunner()


def test_access_plan_and_status_are_machine_readable(tmp_path: Path) -> None:
    plan = runner.invoke(app, ["data", "access-plan", "--json"])
    status = runner.invoke(
        app,
        ["data", "status", "--roots", str(tmp_path / "roots.yaml"), "--json"],
    )
    assert plan.exit_code == 0
    assert len(json.loads(plan.stdout)["actions"]) == 10
    assert status.exit_code == 2
    assert "does not exist" in status.stderr


def test_status_joins_explicit_root_map_and_confirmations(tmp_path: Path) -> None:
    root = tmp_path / "ddr"
    root.mkdir()
    (root / "synthetic.jpg").write_bytes(b"inventory")
    roots = tmp_path / "roots.yaml"
    roots.write_text(f"roots:\n  ddr: '{root.as_posix()}'\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "data",
            "status",
            "--roots",
            str(roots),
            "--license-confirmed",
            "messidor1",
            "--json",
        ],
    )
    assert result.exit_code == 0
    by_id = {item["dataset_id"]: item for item in json.loads(result.stdout)["datasets"]}
    assert by_id["ddr"]["adapter_state"] == "READY"


def test_invalid_root_mapping_fails_closed(tmp_path: Path) -> None:
    roots = tmp_path / "roots.yaml"
    roots.write_text("roots: [not, a, mapping]\n", encoding="utf-8")
    result = runner.invoke(app, ["data", "status", "--roots", str(roots)])
    assert result.exit_code == 2
    assert "dataset_id: local_path" in result.stderr


def test_inspect_build_validate_split_and_verify_commands(tmp_path: Path) -> None:
    missing = runner.invoke(
        app, ["data", "inspect-root", "ddr", str(tmp_path / "missing"), "--json"]
    )
    assert missing.exit_code == 1
    assert json.loads(missing.stdout)["state"] == "MISSING_FILES"

    root = tmp_path / "ddr"
    root.mkdir()
    (root / "synthetic.jpg").write_bytes(b"synthetic-inventory-only")
    dry_run = runner.invoke(
        app,
        [
            "data",
            "build-manifest",
            "ddr",
            str(root),
            str(tmp_path / "manifest"),
            "--dry-run",
            "--json",
        ],
    )
    assert dry_run.exit_code == 0
    assert json.loads(dry_run.stdout)["dry_run"] is True
    assert not (tmp_path / "manifest").exists()

    built = runner.invoke(
        app,
        [
            "data",
            "build-manifest",
            "ddr",
            str(root),
            str(tmp_path / "manifest"),
            "--license-confirmed",
            "--json",
        ],
    )
    assert built.exit_code == 0

    validated = runner.invoke(
        app, ["data", "validate-manifest", str(tmp_path / "manifest"), "--json"]
    )
    proposed = runner.invoke(
        app,
        [
            "data",
            "create-split",
            str(tmp_path / "manifest"),
            str(tmp_path / "split.lock.json"),
            "--dry-run",
            "--json",
        ],
    )
    locked = runner.invoke(
        app,
        [
            "data",
            "create-split",
            str(tmp_path / "manifest"),
            str(tmp_path / "split.lock.json"),
            "--json",
        ],
    )
    verified = runner.invoke(
        app,
        ["data", "verify-split-lock", str(tmp_path / "split.lock.json"), "--json"],
    )
    assert validated.exit_code == proposed.exit_code == locked.exit_code == verified.exit_code == 0
    assert json.loads(validated.stdout)["valid"] is True
    assert json.loads(proposed.stdout)["target_labels_opened"] is False

    duplicates = runner.invoke(
        app,
        [
            "data",
            "audit-duplicates",
            str(tmp_path / "manifest"),
            str(tmp_path / "duplicate-review"),
            "--json",
        ],
    )
    assert duplicates.exit_code == 0
    assert json.loads(duplicates.stdout)["automatic_deletion"] is False


def test_licence_gated_root_fails_without_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "messidor"
    root.mkdir()
    (root / "synthetic.jpg").write_bytes(b"synthetic")
    result = runner.invoke(
        app,
        [
            "data",
            "build-manifest",
            "messidor1",
            str(root),
            str(tmp_path / "manifest"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "LICENSE_REQUIRED" in result.stderr


def test_stage2a_audit_cli_returns_recorded_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_gate(
        output: Path, required: list[str] | None, *, require_review: bool
    ) -> dict[str, Any]:
        assert output == tmp_path / "gate.json"
        assert required == ["3.11", "3.12"]
        assert require_review is True
        return {"final_status": "PASS", "quality_passed": True}

    monkeypatch.setattr(cli, "generate_stage2a_gate", fake_gate)
    result = runner.invoke(
        app,
        [
            "audit",
            "stage2a",
            "--output",
            str(tmp_path / "gate.json"),
            "--required-pythons",
            "3.11,3.12",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["final_status"] == "PASS"
