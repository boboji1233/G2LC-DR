"""Package-content and clean-install audit helpers for Stage 1.6.1."""

from __future__ import annotations

import hashlib
import re
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

WHEEL_LIMIT_BYTES = 2 * 1024 * 1024
SDIST_LIMIT_BYTES = 5 * 1024 * 1024
MAX_SCANNED_MEMBER_BYTES = 5 * 1024 * 1024
CHECKPOINT_SUFFIXES = {".ckpt", ".onnx", ".pt", ".pth", ".safetensors"}
FORBIDDEN_COMPONENTS = {
    ".git",
    ".python",
    ".uv-cache",
    ".package-smoke",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "logs",
    "runs",
}
SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
}
ABSOLUTE_PATH_PATTERNS = {
    "windows_user_path": re.compile(
        rb"(?i)(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\"']+)"
    ),
    "posix_user_path": re.compile(rb"(?:/home/|/Users/)[A-Za-z0-9_.-]+/[^\s\"']+"),
}


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all at once."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_kind(path: Path) -> tuple[str, int]:
    if path.suffix == ".whl":
        return "wheel", WHEEL_LIMIT_BYTES
    if path.name.endswith(".tar.gz"):
        return "sdist", SDIST_LIMIT_BYTES
    raise ValueError(f"unsupported package archive: {path.name}")


def _forbidden_member(name: str) -> str | None:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    parts = tuple(part.lower() for part in pure.parts)
    if pure.is_absolute() or ".." in pure.parts:
        return "unsafe_archive_path"
    if any(part.startswith(".venv") for part in parts):
        return "virtual_environment"
    if any(part in FORBIDDEN_COMPONENTS for part in parts):
        return "generated_or_local_output"
    for index in range(len(parts) - 1):
        if parts[index] == "data" and parts[index + 1] in {"raw", "interim", "processed"}:
            return "medical_data"
    suffix = PurePosixPath(parts[-1]).suffix if parts else ""
    if suffix in CHECKPOINT_SUFFIXES:
        return "checkpoint"
    if suffix == ".log":
        return "log"
    if "review" in (parts[-1] if parts else "") and suffix in {".zip", ".sha256"}:
        return "review_bundle"
    return None


def _member_records(path: Path) -> list[tuple[str, int, bytes]]:
    records: list[tuple[str, int, bytes]] = []
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for zip_member in archive.infolist():
                if zip_member.is_dir():
                    continue
                content = (
                    archive.read(zip_member)
                    if zip_member.file_size <= MAX_SCANNED_MEMBER_BYTES
                    else b""
                )
                records.append((zip_member.filename, zip_member.file_size, content))
        return records
    with tarfile.open(path, mode="r:gz") as archive:
        for tar_member in archive.getmembers():
            if not tar_member.isfile():
                continue
            extracted = archive.extractfile(tar_member)
            content = (
                extracted.read()
                if extracted is not None and tar_member.size <= MAX_SCANNED_MEMBER_BYTES
                else b""
            )
            records.append((tar_member.name, tar_member.size, content))
    return records


def inspect_archive(path: Path, *, workspace_roots: Iterable[Path] = ()) -> dict[str, Any]:
    """Inspect one wheel or sdist for size, member, secret, and local-path violations."""

    path = path.resolve()
    kind, limit = _archive_kind(path)
    records = _member_records(path)
    forbidden: list[dict[str, str]] = []
    content_findings: list[dict[str, str]] = []
    root_needles: list[bytes] = []
    for root in workspace_roots:
        resolved = root.resolve()
        for value in {str(resolved), resolved.as_posix()}:
            root_needles.extend((value.encode(), value.replace("\\", "\\\\").encode()))
    for name, _size, content in records:
        reason = _forbidden_member(name)
        if reason is not None:
            forbidden.append({"path": name, "kind": reason})
        if not content:
            continue
        for finding, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                content_findings.append({"path": name, "kind": finding})
        for finding, pattern in ABSOLUTE_PATH_PATTERNS.items():
            if pattern.search(content):
                content_findings.append({"path": name, "kind": finding})
        if any(needle and needle in content for needle in root_needles):
            content_findings.append({"path": name, "kind": "workspace_path"})
    members = sorted(name for name, _size, _content in records)
    return {
        "kind": kind,
        "path": path.as_posix(),
        "filename": path.name,
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
        "size_limit": limit,
        "within_size_limit": path.stat().st_size < limit,
        "member_count": len(members),
        "members": members,
        "forbidden_members": forbidden,
        "content_findings": content_findings,
        "passed": path.stat().st_size < limit and not forbidden and not content_findings,
    }


def audit_artifact_set(
    paths: Iterable[Path], *, workspace_roots: Iterable[Path] = ()
) -> dict[str, Any]:
    """Require exactly one wheel and one sdist and audit both."""

    inspections = [
        inspect_archive(path, workspace_roots=workspace_roots)
        for path in sorted(paths, key=lambda item: item.name)
    ]
    kinds = [item["kind"] for item in inspections]
    complete = kinds.count("wheel") == 1 and kinds.count("sdist") == 1 and len(kinds) == 2
    return {
        "schema_version": "1.0",
        "limits": {"wheel": WHEEL_LIMIT_BYTES, "sdist": SDIST_LIMIT_BYTES},
        "complete_artifact_set": complete,
        "archives": inspections,
        "passed": complete and all(item["passed"] for item in inspections),
    }
