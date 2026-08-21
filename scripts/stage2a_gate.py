"""Run and record the portable Stage-2A gate for the active Python interpreter."""

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

from g2lc.audit.stage2a import generate_gate

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "audit" / "stage2a"
VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"
ENVIRONMENT = AUDIT / "environments" / f"python_{VERSION.replace('.', '_')}"
LOGS = ENVIRONMENT / "logs"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write(payload: dict[str, Any]) -> None:
    ENVIRONMENT.mkdir(parents=True, exist_ok=True)
    (ENVIRONMENT / "command_results.json").write_text(_canonical(payload) + "\n", encoding="utf-8")


def _record(
    payload: dict[str, Any],
    index: int,
    display: str,
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
) -> int:
    started = time.perf_counter()
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    duration = time.perf_counter() - started
    log_path = LOGS / f"{index:02d}.log"
    log_path.write_text(
        f"$ {display}\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}",
        encoding="utf-8",
    )
    payload["commands"].append(
        {
            "command": display,
            "arguments": [Path(arguments[0]).name, *arguments[1:]],
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
    required = [
        item.strip()
        for item in os.environ.get("G2LC_REQUIRED_PYTHONS", VERSION).split(",")
        if item.strip()
    ]
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
    stage1_environment = dict(os.environ)
    stage1_environment["G2LC_UV"] = uv
    stage1_environment["G2LC_REQUIRED_PYTHONS"] = VERSION
    plan: list[tuple[str, list[str], dict[str, str] | None]] = [
        (
            "uv run python scripts/stage1_6_gate.py",
            [*run, "python", "scripts/stage1_6_gate.py"],
            stage1_environment,
        ),
        (
            f"uv sync --locked --all-groups --python {VERSION}",
            [uv, "sync", "--locked", "--all-groups", "--python", sys.executable],
            None,
        ),
        ("uv run ruff check .", [*run, "ruff", "check", "."], None),
        ("uv run ruff format --check .", [*run, "ruff", "format", "--check", "."], None),
        ("uv run mypy src tests", [*run, "mypy", "src", "tests"], None),
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
            None,
        ),
        (
            "uv run pytest -q tests/stage2a/test_schemas.py",
            [*run, "pytest", "-q", "tests/stage2a/test_schemas.py"],
            None,
        ),
        (
            "uv run pytest -q tests/stage2a/test_adapters.py",
            [*run, "pytest", "-q", "tests/stage2a/test_adapters.py"],
            None,
        ),
        (
            "uv run pytest -q tests/stage2a/test_splits.py",
            [*run, "pytest", "-q", "tests/stage2a/test_splits.py"],
            None,
        ),
        (
            "uv run pytest -q tests/stage2a/test_dedup.py",
            [*run, "pytest", "-q", "tests/stage2a/test_dedup.py"],
            None,
        ),
        (
            "uv run pytest -q tests/stage2a/test_cli.py",
            [*run, "pytest", "-q", "tests/stage2a/test_cli.py"],
            None,
        ),
        (
            "uv run python scripts/stage2a_repository_scan.py",
            [
                *run,
                "python",
                "scripts/stage2a_repository_scan.py",
                "--output",
                str(AUDIT / "repository_scan.json"),
            ],
            None,
        ),
        (
            "uv build --out-dir <isolated-package-dir>",
            [uv, "build", "--python", sys.executable, "--out-dir", str(package_directory)],
            None,
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
            None,
        ),
    ]
    for index, (display, arguments, environment) in enumerate(plan, start=1):
        _record(payload, index, display, arguments, environment=environment)

    gate_path = AUDIT / "gate.json"
    preliminary = generate_gate(gate_path, required, require_review=False)
    if preliminary["quality_passed"]:
        review = [*run, "python", "scripts/review_bundle.py", "--stage", "2a"]
        _record(payload, len(plan) + 1, "uv run python scripts/review_bundle.py --stage 2a", review)
        _record(
            payload,
            len(plan) + 2,
            "uv run python scripts/review_bundle.py --stage 2a --finalize",
            [*review, "--finalize"],
        )
    gate = generate_gate(gate_path, required, require_review=True)
    return 0 if gate["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
