"""Build and independently verify a commit-bound, privacy-safe review bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "artifacts" / "review"
MAX_FILE_BYTES = 5 * 1024 * 1024
DENIED_SUFFIXES = {".ckpt", ".onnx", ".pt", ".pth", ".safetensors"}
SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
}
LOCAL_PATH_PATTERNS = {
    "windows_user_path": re.compile(
        rb"(?i)(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\"']+)"
    ),
    "posix_user_path": re.compile(rb"(?:/home/|/Users/)[A-Za-z0-9_.-]+/[^\s\"']+"),
}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _git_available() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _debug_files() -> list[Path]:
    roots = ["src", "tests", "scripts", "docs", ".github", "examples", "knowledge"]
    top_level = [
        "pyproject.toml",
        "uv.lock",
        "Makefile",
        "README.md",
        "STATUS.md",
        "CHANGELOG.md",
        "IMPLEMENTATION_PLAN.md",
        "THEORY_TO_TEST_MATRIX.md",
        "AUDIT_REPORT_STAGE1_5.md",
        "AUDIT_REPORT_STAGE1_6.md",
        "OWNER_ACTIONS_AFTER_STAGE1_6.md",
    ]
    files: list[Path] = []
    for name in roots:
        root = ROOT / name
        if root.exists():
            files.extend(root.rglob("*"))
    files.extend(ROOT / name for name in top_level if (ROOT / name).is_file())
    return files


def _files(stage: str, *, git_available: bool) -> list[Path]:
    tracked = (
        [ROOT / item for item in _git("ls-files").splitlines() if item]
        if git_available
        else _debug_files()
    )
    audit_names = {"stage1_6"}
    audit_names.add(f"stage{stage.replace('.', '_')}")
    generated = [
        item
        for name in audit_names
        for item in (ROOT / "artifacts" / "audit" / name).rglob("*")
        if (ROOT / "artifacts" / "audit" / name).is_dir()
    ]
    excluded_parts = {
        ".git",
        ".python",
        ".uv-cache",
        ".package-smoke",
        ".review-verify",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "packages",
    }
    return sorted(
        {
            path.resolve()
            for path in [*tracked, *generated]
            if path.is_file()
            and not excluded_parts.intersection(path.parts)
            and not any(part.startswith(".venv") for part in path.parts)
            and path.suffix not in {".pyc", ".pyo"}
        },
        key=lambda item: item.relative_to(ROOT).as_posix(),
    )


def _normalize_text(value: str) -> str:
    replacements = sorted(
        {
            str(ROOT.resolve()): "<WORKSPACE>",
            ROOT.resolve().as_posix(): "<WORKSPACE>",
            str(ROOT.parent.resolve()): "<WORKSPACE_PARENT>",
            ROOT.parent.resolve().as_posix(): "<WORKSPACE_PARENT>",
        }.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for source, target in replacements:
        value = value.replace(source, target).replace(source.replace("\\", "\\\\"), target)
    value = re.sub(
        r"(?i)\b[A-Z]:(?:\\\\|\\|/)[^\s\"']+",
        "<LOCAL_PATH>",
        value,
    )
    return re.sub(r"(?:/home/|/Users/)[A-Za-z0-9_.-]+/[^\s\"']+", "<LOCAL_PATH>", value)


def _normalize_json(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_json(item) for key, item in value.items()}
    return value


def _externalize_gate(payload: dict[str, Any], final_metadata_name: str) -> dict[str, Any]:
    for key in ("bundle_summary", "review_bundle_artifact"):
        current = payload.get(key)
        if isinstance(current, dict):
            payload[key] = {
                **current,
                "sha256": "EXTERNALIZED",
                "checksum_matches": None,
                "checksum_authority": "external_sha256_and_final_metadata",
                "final_metadata": f"artifacts/review/{final_metadata_name}",
                "recursive_checksum_externalized": True,
            }
    payload["embedded_review_bundle_checksum"] = {
        "value": "EXTERNALIZED",
        "authority": "external_sha256_and_final_metadata",
        "final_metadata": f"artifacts/review/{final_metadata_name}",
    }
    return payload


def _archive_bytes(path: Path, final_metadata_name: str) -> bytes:
    relative = path.relative_to(ROOT).as_posix()
    content = path.read_bytes()
    if path.suffix == ".json":
        with suppress(UnicodeDecodeError, json.JSONDecodeError):
            payload = json.loads(content.decode("utf-8"))
            if relative == "artifacts/audit/stage1_6/gate.json":
                payload = _externalize_gate(payload, final_metadata_name)
            return (
                json.dumps(
                    _normalize_json(payload),
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode()
    if b"\x00" not in content:
        with suppress(UnicodeDecodeError):
            content = _normalize_text(content.decode("utf-8")).encode()
    return content


def _scan(entries: dict[str, bytes]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for relative, content in entries.items():
        suffix = Path(relative).suffix.lower()
        if len(content) > MAX_FILE_BYTES:
            findings.append({"path": relative, "kind": "oversize"})
        if suffix in DENIED_SUFFIXES:
            findings.append({"path": relative, "kind": "checkpoint"})
        if relative.startswith(("data/raw/", "data/interim/", "data/processed/")) and (
            Path(relative).name != ".gitkeep"
        ):
            findings.append({"path": relative, "kind": "medical_data"})
        if len(content) <= MAX_FILE_BYTES:
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(content):
                    findings.append({"path": relative, "kind": name})
            for name, pattern in LOCAL_PATH_PATTERNS.items():
                if pattern.search(content):
                    findings.append({"path": relative, "kind": name})
    return {"passed": not findings, "findings": findings}


def _metadata(
    stage: str,
    scan: dict[str, Any],
    *,
    git_available: bool,
    finalize: bool,
    checksum_name: str,
    final_metadata_name: str,
) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD") if git_available else None
    status = _git("status", "--short", "--untracked-files=no") if git_available else ""
    github_ref = os.environ.get("GITHUB_REF", "")
    github_sha = os.environ.get("GITHUB_SHA")
    return {
        "schema_version": "1.0",
        "stage": stage,
        "publishable": git_available,
        "finalization_pass": finalize,
        "git_commit": head,
        "git_branch": _git("branch", "--show-current") if git_available else None,
        "dirty_tracked_worktree": bool(status),
        "pr_head_sha": os.environ.get("GITHUB_HEAD_SHA") or head,
        "pr_merge_sha": github_sha if github_ref.startswith("refs/pull/") else None,
        "privacy_scan": scan,
        "archive_checksum": {
            "value": "EXTERNALIZED",
            "authority": "external_sha256_and_final_metadata",
            "checksum_file": checksum_name,
            "final_metadata_file": final_metadata_name,
        },
        "path_normalization": {
            "archive_only": True,
            "placeholder": "<WORKSPACE>",
            "raw_evidence_unchanged": True,
        },
    }


def _verification_basetemp(run_id: str) -> Path:
    return ROOT.parent / ".review-pytest" / run_id


def _verify_archive(archive: Path, expected: dict[str, str], metadata_name: str) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    destination = ROOT / ".review-verify" / run_id
    basetemp = _verification_basetemp(run_id)
    basetemp.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    mismatches = [
        path
        for path, digest in expected.items()
        if not (destination / path).is_file() or _hash(destination / path) != digest
    ]
    metadata = json.loads((destination / metadata_name).read_text(encoding="utf-8"))
    embedded_gate_path = destination / "artifacts" / "audit" / "stage1_6" / "gate.json"
    embedded_gate = (
        json.loads(embedded_gate_path.read_text(encoding="utf-8"))
        if embedded_gate_path.is_file()
        else {}
    )
    recursive_checksum_externalized = metadata.get("archive_checksum", {}).get("value") == (
        "EXTERNALIZED"
    ) and embedded_gate.get("embedded_review_bundle_checksum", {}).get("value") == ("EXTERNALIZED")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(destination / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--basetemp",
            str(basetemp),
            "tests/stage1_6/test_cross_path_regressions.py",
        ],
        cwd=destination,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "passed": not mismatches and result.returncode == 0 and recursive_checksum_externalized,
        "manifest_mismatches": mismatches,
        "semantic_test_exit_code": result.returncode,
        "semantic_test_output": (result.stdout + result.stderr)[-4000:],
        "embedded_commit": metadata["git_commit"],
        "recursive_checksum_externalized": recursive_checksum_externalized,
        "embedded_checksum_authority": metadata["archive_checksum"]["authority"],
        "verification_workspace": "<WORKSPACE>/.review-verify/<RUN_ID>",
        "pytest_basetemp": "<WORKSPACE_PARENT>/.review-pytest/<RUN_ID>",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["1.5", "1.6", "1.6.1"], default="1.6.1")
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Rebuild after the preliminary gate and first verified bundle exist.",
    )
    parser.add_argument(
        "--allow-no-git",
        action="store_true",
        help="Create a clearly non-publishable debug archive outside a Git checkout.",
    )
    arguments = parser.parse_args()
    stage = arguments.stage
    REVIEW.mkdir(parents=True, exist_ok=True)
    git_available = _git_available()
    if not git_available and not arguments.allow_no_git:
        raise RuntimeError("review bundle requires a Git checkout; use --allow-no-git for debug")
    short_head = _git("rev-parse", "--short=12", "HEAD") if git_available else "DEBUG_NO_GIT"
    if git_available and _git("status", "--short", "--untracked-files=no"):
        raise RuntimeError("review bundle requires a clean tracked worktree")
    selected = _files(stage, git_available=git_available)
    stage_token = stage.replace(".", "_")
    stem = (
        f"G2LC_DR_STAGE{stage_token}_REVIEW_{short_head}"
        if git_available
        else f"G2LC_DR_STAGE{stage_token}_{short_head}"
    )
    archive = REVIEW / f"{stem}.zip"
    checksum = REVIEW / f"{stem}.sha256"
    manifest = REVIEW / f"{stem}_manifest.tsv"
    embedded_metadata_path = REVIEW / f"{stem}_embedded_metadata.json"
    final_metadata_path = REVIEW / f"{stem}_final_metadata.json"
    final_metadata_name = final_metadata_path.name
    entries = {
        path.relative_to(ROOT).as_posix(): _archive_bytes(path, final_metadata_name)
        for path in selected
    }
    scan = _scan(entries)
    if not scan["passed"]:
        raise RuntimeError(f"privacy/safety scan failed: {scan['findings']}")
    rows = ["path\tsha256\tsize"]
    expected: dict[str, str] = {}
    for relative, content in sorted(entries.items()):
        digest = hashlib.sha256(content).hexdigest()
        expected[relative] = digest
        rows.append(f"{relative}\t{digest}\t{len(content)}")
    manifest_text = "\n".join(rows) + "\n"
    metadata = _metadata(
        stage,
        scan,
        git_available=git_available,
        finalize=arguments.finalize,
        checksum_name=checksum.name,
        final_metadata_name=final_metadata_name,
    )
    metadata_name = f"{stem}_metadata.json"
    metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    manifest.write_text(manifest_text, encoding="utf-8")
    embedded_metadata_path.write_text(metadata_text, encoding="utf-8")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative, content in sorted(entries.items()):
            bundle.writestr(relative, content)
        bundle.writestr(f"{stem}_manifest.tsv", manifest_text)
        bundle.writestr(metadata_name, metadata_text)
    verification = _verify_archive(archive, expected, metadata_name)
    if not verification["passed"]:
        raise RuntimeError(f"review bundle verification failed: {verification}")
    digest = _hash(archive)
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    final_metadata = {
        "schema_version": "1.0",
        "authority": "external_sha256_and_final_metadata",
        "archive": {
            "path": archive.name,
            "sha256": digest,
            "size": archive.stat().st_size,
        },
        "checksum_file": checksum.name,
        "embedded_checksum_value": "EXTERNALIZED",
        "git_commit": metadata["git_commit"],
        "git_branch": metadata["git_branch"],
        "finalization_pass": arguments.finalize,
        "manifest_sha256": hashlib.sha256(manifest_text.encode()).hexdigest(),
        "path_normalization": metadata["path_normalization"],
    }
    final_metadata_path.write_text(
        json.dumps(final_metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    verification.update(
        {
            "archive_sha256": digest,
            "checksum_matches": checksum.read_text(encoding="utf-8").split()[0] == digest,
            "final_metadata_matches": final_metadata["archive"]["sha256"] == digest,
            "final_metadata_path": final_metadata_path.relative_to(ROOT).as_posix(),
        }
    )
    verification["passed"] = bool(
        verification["passed"]
        and verification["checksum_matches"]
        and verification["final_metadata_matches"]
    )
    verification_path = REVIEW / f"{stem}_verification.json"
    verification_path.write_text(
        json.dumps(verification, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(archive.relative_to(ROOT).as_posix())
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
