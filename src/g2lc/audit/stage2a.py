"""Aggregate recorded Stage-2A data-governance evidence without self-assertion."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from g2lc.utils.io import canonical_json, sha256_file

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "artifacts" / "audit" / "stage2a"
MANDATORY_COMMAND_MARKERS = (
    "uv run python scripts/stage1_6_gate.py",
    "uv sync --locked --all-groups --python",
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run mypy src tests",
    "uv run pytest -q --cov-branch --cov=g2lc --cov=g2lc_verifier",
    "uv run pytest -q tests/stage2a/test_schemas.py",
    "uv run pytest -q tests/stage2a/test_adapters.py",
    "uv run pytest -q tests/stage2a/test_splits.py",
    "uv run pytest -q tests/stage2a/test_dedup.py",
    "uv run pytest -q tests/stage2a/test_cli.py",
    "uv run python scripts/stage2a_repository_scan.py",
    "uv build --out-dir",
    "uv run python scripts/package_audit.py --artifact-dir",
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "UNAVAILABLE"


def _environment(version: str) -> dict[str, Any]:
    root = AUDIT / "environments" / f"python_{version.replace('.', '_')}"
    evidence = _read_json(root / "command_results.json")
    commands = evidence.get("commands", []) if isinstance(evidence.get("commands"), list) else []
    command_by_name: dict[str, dict[str, Any]] = {}
    for item in commands:
        if not isinstance(item, dict):
            continue
        name = item.get("command")
        if isinstance(name, str):
            command_by_name[name] = item
    missing = [
        marker
        for marker in MANDATORY_COMMAND_MARKERS
        if not any(marker in name for name in command_by_name)
    ]
    failed = [name for name, result in command_by_name.items() if result.get("exit_code") != 0]
    package_audit = _read_json(root / "package_audit.json")
    return {
        "required_python": version,
        "recorded_python": evidence.get("python_version"),
        "uv_version": evidence.get("uv_version"),
        "commands": commands,
        "missing_command_markers": missing,
        "failed_commands": failed,
        "package_audit": package_audit,
        "passed": bool(evidence)
        and not missing
        and not failed
        and package_audit.get("passed") is True,
    }


def _review_bundle(head: str) -> dict[str, Any]:
    short = head[:12]
    stem = f"G2LC_DR_STAGE2A_REVIEW_{short}"
    archive = ROOT / "artifacts" / "review" / f"{stem}.zip"
    checksum = ROOT / "artifacts" / "review" / f"{stem}.sha256"
    metadata_path = ROOT / "artifacts" / "review" / f"{stem}_final_metadata.json"
    verification_path = ROOT / "artifacts" / "review" / f"{stem}_verification.json"
    metadata = _read_json(metadata_path)
    verification = _read_json(verification_path)
    actual_hash = sha256_file(archive) if archive.is_file() else None
    checksum_hash = (
        checksum.read_text(encoding="utf-8").split()[0]
        if checksum.is_file() and checksum.read_text(encoding="utf-8").split()
        else None
    )
    return {
        "archive": archive.relative_to(ROOT).as_posix(),
        "sha256": actual_hash,
        "checksum_file": checksum.relative_to(ROOT).as_posix(),
        "final_metadata": metadata_path.relative_to(ROOT).as_posix(),
        "verification": verification_path.relative_to(ROOT).as_posix(),
        "checksum_matches": actual_hash is not None
        and checksum_hash == actual_hash
        and metadata.get("archive", {}).get("sha256") == actual_hash,
        "verified": verification.get("passed") is True,
        "finalized": metadata.get("finalization_pass") is True,
    }


def generate_gate(
    output: str | Path = "artifacts/audit/stage2a/gate.json",
    required_pythons: list[str] | None = None,
    *,
    require_review: bool = True,
) -> dict[str, Any]:
    """Aggregate immutable logs, package audits, and review hashes."""

    required = required_pythons or [
        item.strip()
        for item in os.environ.get("G2LC_REQUIRED_PYTHONS", "3.11,3.12").split(",")
        if item.strip()
    ]
    head = _git("rev-parse", "HEAD")
    environments = {version: _environment(version) for version in required}
    stage1 = _read_json(ROOT / "artifacts" / "audit" / "stage1_6" / "gate.json")
    repository_scan = _read_json(AUDIT / "repository_scan.json")
    review = _review_bundle(head)
    tracked_status = _git("status", "--short", "--untracked-files=no")
    quality_passed = (
        stage1.get("final_status") == "PASS"
        and repository_scan.get("passed") is True
        and all(item["passed"] for item in environments.values())
    )
    review_passed = review["checksum_matches"] and review["verified"] and review["finalized"]
    final_status = "PASS" if quality_passed and (review_passed or not require_review) else "FAIL"
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "stage": "2A_DATA_GOVERNANCE_ORACLE_INPUT_READINESS",
        "final_status": final_status,
        "quality_passed": quality_passed,
        "review_required": require_review,
        "git": {
            "commit": head,
            "branch": _git("branch", "--show-current"),
            "tracked_worktree_clean": not bool(tracked_status),
        },
        "uv_lock_sha256": sha256_file(ROOT / "uv.lock"),
        "stage1_6_1": {
            "final_status": stage1.get("final_status"),
            "git_commit": stage1.get("git_commit"),
            "gate_sha256": sha256_file(ROOT / "artifacts" / "audit" / "stage1_6" / "gate.json")
            if stage1
            else None,
        },
        "required_pythons": required,
        "environments": environments,
        "repository_scan": repository_scan,
        "review_bundle": review,
        "scope_assertions": {
            "datasets_downloaded": False,
            "clinical_labels_fabricated": False,
            "oracle_executed": False,
            "models_or_training_added": False,
            "duplicate_files_deleted": False,
            "embedding_deduplication": "NOT_RUN",
        },
    }
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return payload
