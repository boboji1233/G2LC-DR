"""Run and record the exact Stage-1.6 gate for the active Python interpreter."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from g2lc.audit.stage1_6 import generate_gate

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "audit" / "stage1_6"
VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"
ENVIRONMENT = AUDIT / "environments" / f"python_{VERSION.replace('.', '_')}"
LOGS = ENVIRONMENT / "logs"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write(payload: dict[str, Any]) -> None:
    ENVIRONMENT.mkdir(parents=True, exist_ok=True)
    (ENVIRONMENT / "command_results.json").write_text(_canonical(payload) + "\n", encoding="utf-8")


def _record(
    payload: dict[str, Any], uv: str, index: int, display: str, arguments: list[str]
) -> int:
    started = time.perf_counter()
    result = subprocess.run(arguments, cwd=ROOT, text=True, capture_output=True, check=False)
    duration = time.perf_counter() - started
    log_path = LOGS / f"{index:02d}.log"
    log_path.write_text(
        f"$ {display}\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}",
        encoding="utf-8",
    )
    payload["commands"].append(
        {
            "command": display,
            "arguments": [Path(uv).name, *arguments[1:]],
            "exit_code": result.returncode,
            "duration_seconds": round(duration, 6),
            "log": log_path.relative_to(ENVIRONMENT).as_posix(),
        }
    )
    _write(payload)
    print(f"[{result.returncode}] {display}", flush=True)
    return result.returncode


def main() -> int:
    uv = os.environ.get("G2LC_UV") or shutil.which("uv")
    if uv is None:
        print("ERROR: uv is not available", file=sys.stderr)
        return 2
    LOGS.mkdir(parents=True, exist_ok=True)
    uv_version = subprocess.run(
        [uv, "--version"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "uv_version": uv_version.stdout.strip(),
        "commands": [],
    }
    run = [uv, "run", "--python", sys.executable]
    package_directory = ENVIRONMENT / "packages" / f"run_{time.time_ns()}"
    package_audit_path = ENVIRONMENT / "package_audit.json"
    required = [
        item.strip() for item in os.environ.get("G2LC_REQUIRED_PYTHONS", VERSION).split(",")
    ]
    plan = [
        (
            f"uv sync --locked --all-groups --python {VERSION}",
            [uv, "sync", "--locked", "--all-groups", "--python", sys.executable],
        ),
        ("uv run ruff check .", [*run, "ruff", "check", "."]),
        ("uv run ruff format --check .", [*run, "ruff", "format", "--check", "."]),
        ("uv run mypy src tests", [*run, "mypy", "src", "tests"]),
        (
            "uv run pytest -q --cov-branch --cov=g2lc --cov=g2lc_verifier",
            [
                *run,
                "pytest",
                "-q",
                "--cov-branch",
                "--cov=g2lc",
                "--cov=g2lc_verifier",
                "--cov-report=term-missing",
                f"--cov-report=json:{ENVIRONMENT / 'coverage.json'}",
                f"--junitxml={ENVIRONMENT / 'junit.xml'}",
                "--cov-fail-under=92",
            ],
        ),
        (
            "uv build --out-dir <isolated-package-dir>",
            [
                uv,
                "build",
                "--python",
                sys.executable,
                "--out-dir",
                str(package_directory),
            ],
        ),
        (
            "uv run python scripts/package_audit.py --artifact-dir <isolated-package-dir>",
            [
                *run,
                "python",
                "scripts/package_audit.py",
                "--artifact-dir",
                str(package_directory),
                "--output",
                str(package_audit_path),
                "--uv",
                uv,
                "--python",
                sys.executable,
            ],
        ),
        (
            "uv run g2lc synthetic matrix --random-seeds 20 --semantic-generated-cases 200",
            [
                *run,
                "g2lc",
                "synthetic",
                "matrix",
                "--random-seeds",
                "20",
                "--semantic-generated-cases",
                "200",
                "--json",
            ],
        ),
        (
            "uv run g2lc audit stage1-6 --output artifacts/audit/stage1_6/gate.json",
            [
                *run,
                "g2lc",
                "audit",
                "stage1-6",
                "--required-pythons",
                ",".join(required),
                "--output",
                "artifacts/audit/stage1_6/gate.json",
            ],
        ),
    ]
    for index, (display, arguments) in enumerate(plan, start=1):
        _record(payload, uv, index, display, arguments)
    gate_path = AUDIT / "gate.json"
    generate_gate(gate_path, required)
    review_arguments = [*run, "python", "scripts/review_bundle.py", "--stage", "1.6.1"]
    finalize_arguments = [*review_arguments, "--finalize"]
    _record(
        payload,
        uv,
        len(plan) + 1,
        "uv run python scripts/review_bundle.py --stage 1.6.1",
        review_arguments,
    )
    generate_gate(gate_path, required)
    _record(
        payload,
        uv,
        len(plan) + 2,
        "uv run python scripts/review_bundle.py --stage 1.6.1 --finalize",
        finalize_arguments,
    )
    gate = generate_gate(gate_path, required)
    return 0 if gate["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
