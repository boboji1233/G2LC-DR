"""Build and independently verify a commit-bound, privacy-safe review bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "artifacts" / "review"
MAX_FILE_BYTES = 5 * 1024 * 1024
DENIED_SUFFIXES = {".ckpt", ".onnx", ".pt", ".pth"}
SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
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
    audit = ROOT / "artifacts" / "audit" / f"stage{stage.replace('.', '_')}"
    generated = list(audit.rglob("*")) if audit.is_dir() else []
    excluded_parts = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
    return sorted(
        {
            path.resolve()
            for path in [*tracked, *generated]
            if path.is_file()
            and not excluded_parts.intersection(path.parts)
            and path.suffix not in {".pyc", ".pyo"}
        },
        key=lambda item: item.relative_to(ROOT).as_posix(),
    )


def _scan(files: list[Path]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.stat().st_size > MAX_FILE_BYTES:
            findings.append({"path": relative, "kind": "oversize"})
        if path.suffix.lower() in DENIED_SUFFIXES:
            findings.append({"path": relative, "kind": "checkpoint"})
        if relative.startswith(("data/raw/", "data/interim/", "data/processed/")) and (
            path.name != ".gitkeep"
        ):
            findings.append({"path": relative, "kind": "medical_data"})
        if path.stat().st_size <= MAX_FILE_BYTES:
            content = path.read_bytes()
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(content):
                    findings.append({"path": relative, "kind": name})
    return {"passed": not findings, "findings": findings}


def _metadata(
    stage: str, scan: dict[str, Any], *, git_available: bool, finalize: bool
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
    }


def _verify_archive(archive: Path, expected: dict[str, str], metadata_name: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="g2lc-review-") as temporary:
        destination = Path(temporary)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
        mismatches = [
            path
            for path, digest in expected.items()
            if not (destination / path).is_file() or _hash(destination / path) != digest
        ]
        metadata = json.loads((destination / metadata_name).read_text(encoding="utf-8"))
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(destination / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/stage1_6/test_cross_path_regressions.py",
            ],
            cwd=destination,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "passed": not mismatches and result.returncode == 0,
            "manifest_mismatches": mismatches,
            "semantic_test_exit_code": result.returncode,
            "semantic_test_output": (result.stdout + result.stderr)[-4000:],
            "embedded_commit": metadata["git_commit"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["1.5", "1.6"], default="1.6")
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
    scan = _scan(selected)
    if not scan["passed"]:
        raise RuntimeError(f"privacy/safety scan failed: {scan['findings']}")
    stage_token = stage.replace(".", "_")
    stem = (
        f"G2LC_DR_STAGE{stage_token}_REVIEW_{short_head}"
        if git_available
        else f"G2LC_DR_STAGE{stage_token}_{short_head}"
    )
    archive = REVIEW / f"{stem}.zip"
    checksum = REVIEW / f"{stem}.sha256"
    manifest = REVIEW / f"{stem}_manifest.tsv"
    metadata_path = REVIEW / f"{stem}_metadata.json"
    rows = ["path\tsha256\tsize"]
    expected: dict[str, str] = {}
    for path in selected:
        relative = path.relative_to(ROOT).as_posix()
        digest = _hash(path)
        expected[relative] = digest
        rows.append(f"{relative}\t{digest}\t{path.stat().st_size}")
    manifest_text = "\n".join(rows) + "\n"
    metadata = _metadata(
        stage,
        scan,
        git_available=git_available,
        finalize=arguments.finalize,
    )
    metadata_name = f"{stem}_metadata.json"
    metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    manifest.write_text(manifest_text, encoding="utf-8")
    metadata_path.write_text(metadata_text, encoding="utf-8")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in selected:
            bundle.write(path, path.relative_to(ROOT).as_posix())
        bundle.writestr(f"{stem}_manifest.tsv", manifest_text)
        bundle.writestr(metadata_name, metadata_text)
    verification = _verify_archive(archive, expected, metadata_name)
    verification_path = REVIEW / f"{stem}_verification.json"
    verification_path.write_text(
        json.dumps(verification, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if not verification["passed"]:
        raise RuntimeError(f"review bundle verification failed: {verification}")
    digest = _hash(archive)
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(archive.relative_to(ROOT).as_posix())
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
