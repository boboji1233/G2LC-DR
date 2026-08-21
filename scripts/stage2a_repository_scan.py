"""Fail closed on tracked medical data, checkpoints, secrets, and local user paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_SCAN_BYTES = 5 * 1024 * 1024
DENIED_SUFFIXES = {".ckpt", ".onnx", ".pt", ".pth", ".safetensors"}
MEDICAL_ROOTS = ("data/raw/", "data/interim/", "data/processed/")
PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "windows_user_path": re.compile(
        rb"(?i)(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\"']+)"
    ),
    "posix_user_path": re.compile(rb"(?:/home/|/Users/)[A-Za-z0-9_.-]+/[^\s\"']+"),
}


def _tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def scan_repository() -> dict[str, Any]:
    """Return deterministic findings without reading ignored or untracked datasets."""

    findings: list[dict[str, str]] = []
    hashes: dict[str, str] = {}
    for path in _tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            continue
        content = path.read_bytes()
        hashes[relative] = hashlib.sha256(content).hexdigest()
        if path.suffix.lower() in DENIED_SUFFIXES:
            findings.append({"path": relative, "kind": "checkpoint"})
        if relative.startswith(MEDICAL_ROOTS) and path.name != ".gitkeep":
            findings.append({"path": relative, "kind": "medical_data"})
        if len(content) <= MAX_SCAN_BYTES:
            for kind, pattern in PATTERNS.items():
                if pattern.search(content):
                    findings.append({"path": relative, "kind": kind})
    return {
        "schema_version": "1.0",
        "passed": not findings,
        "tracked_files_scanned": len(hashes),
        "tracked_tree_hash": hashlib.sha256(
            json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "findings": sorted(findings, key=lambda item: (item["path"], item["kind"])),
        "ignored_and_untracked_roots_opened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/audit/stage2a/repository_scan.json")
    )
    arguments = parser.parse_args()
    payload = scan_repository()
    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
