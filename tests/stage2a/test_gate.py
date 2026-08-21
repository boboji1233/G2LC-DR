from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from g2lc.audit import stage2a
from g2lc.utils.io import sha256_file


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_stage2a_gate_aggregates_real_environment_and_review_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = tmp_path / "artifacts" / "audit" / "stage2a"
    monkeypatch.setattr(stage2a, "ROOT", tmp_path)
    monkeypatch.setattr(stage2a, "AUDIT", audit)
    head = "a" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return head
        if arguments == ("branch", "--show-current"):
            return "codex/stage2-data-governance"
        return ""

    monkeypatch.setattr(stage2a, "_git", fake_git)
    (tmp_path / "uv.lock").write_text("locked", encoding="utf-8")
    _write_json(
        tmp_path / "artifacts" / "audit" / "stage1_6" / "gate.json",
        {"final_status": "PASS", "git_commit": head},
    )
    _write_json(audit / "repository_scan.json", {"passed": True, "findings": []})
    commands = [
        {"command": marker, "exit_code": 0, "duration_seconds": 0.1}
        for marker in stage2a.MANDATORY_COMMAND_MARKERS
    ]
    for version in ("3.11", "3.12"):
        environment = audit / "environments" / f"python_{version.replace('.', '_')}"
        _write_json(
            environment / "command_results.json",
            {"python_version": version, "uv_version": "uv 0.12.5", "commands": commands},
        )
        _write_json(environment / "package_audit.json", {"passed": True})

    stem = f"G2LC_DR_STAGE2A_REVIEW_{head[:12]}"
    review = tmp_path / "artifacts" / "review"
    review.mkdir(parents=True)
    archive = review / f"{stem}.zip"
    archive.write_bytes(b"synthetic-review")
    digest = sha256_file(archive)
    (review / f"{stem}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    _write_json(
        review / f"{stem}_final_metadata.json",
        {"archive": {"sha256": digest}, "finalization_pass": True},
    )
    _write_json(review / f"{stem}_verification.json", {"passed": True})

    gate = stage2a.generate_gate(audit / "gate.json", ["3.11", "3.12"])
    assert gate["final_status"] == "PASS"
    assert gate["review_bundle"]["checksum_matches"] is True
    assert gate["scope_assertions"]["oracle_executed"] is False


def test_stage2a_environment_fails_closed_on_missing_or_failed_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = tmp_path / "audit"
    monkeypatch.setattr(stage2a, "AUDIT", audit)
    _write_json(
        audit / "environments" / "python_3_11" / "command_results.json",
        {"commands": [{"command": "uv run ruff check .", "exit_code": 1}]},
    )
    result = stage2a._environment("3.11")
    assert result["passed"] is False
    assert result["failed_commands"] == ["uv run ruff check ."]
    assert result["missing_command_markers"]


def test_stage2a_git_helper_does_not_invent_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="denied"),
    )
    assert stage2a._git("rev-parse", "HEAD") == "UNAVAILABLE"
