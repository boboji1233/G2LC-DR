"""Audit package contents and run clean, installed-CLI smoke tests."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from g2lc.audit.package import audit_artifact_set

ROOT = Path(__file__).resolve().parents[1]


def _portable(value: str) -> str:
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
    return value


def _run(arguments: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(arguments, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "arguments": [_portable(item) for item in arguments],
        "exit_code": result.returncode,
        "duration_seconds": round(time.perf_counter() - started, 6),
        "stdout": _portable(result.stdout[-4000:]),
        "stderr": _portable(result.stderr[-4000:]),
    }


def _smoke(uv: Path, python: Path, artifact: Path, work_root: Path) -> dict[str, Any]:
    artifact_root = work_root / f"{artifact.suffix.lstrip('.')}-{uuid.uuid4().hex}"
    artifact_root.mkdir(parents=True, exist_ok=False)
    prefix = [
        str(uv),
        "run",
        "--no-project",
        "--isolated",
        "--python",
        str(python),
        "--with",
        str(artifact),
    ]
    version = _run([*prefix, "g2lc", "version"], cwd=artifact_root)
    synthetic = _run(
        [*prefix, "g2lc", "synthetic", "run", "--fixture", "minimal_dr", "--json"],
        cwd=artifact_root,
    )
    version_value = version["stdout"].strip()
    return {
        "artifact": artifact.name,
        "work_root": _portable(str(artifact_root)),
        "version_command": version,
        "synthetic_command": synthetic,
        "reported_version": version_value,
        "passed": version["exit_code"] == 0
        and version_value == "0.1.0"
        and synthetic["exit_code"] == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    arguments = parser.parse_args()
    artifacts = [
        *arguments.artifact_dir.glob("*.whl"),
        *arguments.artifact_dir.glob("*.tar.gz"),
    ]
    audit = audit_artifact_set(artifacts, workspace_roots=[ROOT, ROOT.parent])
    for archive in audit["archives"]:
        archive["path"] = _portable(archive["path"])
    smoke_root = ROOT / ".package-smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    smoke = (
        [
            _smoke(arguments.uv.resolve(), arguments.python.resolve(), path.resolve(), smoke_root)
            for path in sorted(artifacts, key=lambda item: item.name)
        ]
        if audit["passed"]
        else []
    )
    payload = {
        **audit,
        "schema_version": "1.1",
        "python": sys.version.split()[0],
        "clean_install_smoke": smoke,
        "passed": audit["passed"] and len(smoke) == 2 and all(item["passed"] for item in smoke),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
