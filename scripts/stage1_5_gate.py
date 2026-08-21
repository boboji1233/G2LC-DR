"""Portable runner for the exact Stage-1.5 command plan."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "audit" / "stage1_5"
LOGS = AUDIT / "logs"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_results(payload: dict[str, Any]) -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "command_results.json").write_text(_canonical(payload) + "\n", encoding="utf-8")


def main() -> int:
    uv = os.environ.get("G2LC_UV") or shutil.which("uv")
    if uv is None:
        print("ERROR: uv is not available; set G2LC_UV to its executable path", file=sys.stderr)
        return 2
    LOGS.mkdir(parents=True, exist_ok=True)
    uv_version_result = subprocess.run(
        [uv, "--version"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "uv_executable": Path(uv).name,
        "uv_version": uv_version_result.stdout.strip(),
        "commands": [],
    }
    plan = [
        ("uv sync --locked --all-groups", [uv, "sync", "--locked", "--all-groups"]),
        ("uv run ruff check .", [uv, "run", "ruff", "check", "."]),
        (
            "uv run ruff format --check .",
            [uv, "run", "ruff", "format", "--check", "."],
        ),
        ("uv run mypy src tests", [uv, "run", "mypy", "src", "tests"]),
        (
            "uv run pytest -q --cov=g2lc --cov=g2lc_verifier --cov-branch "
            "--cov-report=term-missing "
            "--cov-report=json:artifacts/audit/stage1_5/coverage.json --cov-fail-under=90",
            [
                uv,
                "run",
                "pytest",
                "-q",
                "--cov=g2lc",
                "--cov=g2lc_verifier",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-report=json:artifacts/audit/stage1_5/coverage.json",
                "--cov-fail-under=90",
            ],
        ),
        ("uv build", [uv, "build"]),
        ("uv run g2lc synthetic matrix", [uv, "run", "g2lc", "synthetic", "matrix"]),
        (
            "uv run g2lc audit stage1-5 --output artifacts/audit/stage1_5/gate.json",
            [
                uv,
                "run",
                "g2lc",
                "audit",
                "stage1-5",
                "--output",
                "artifacts/audit/stage1_5/gate.json",
            ],
        ),
    ]
    for index, (display, arguments) in enumerate(plan, start=1):
        result = subprocess.run(
            arguments,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        display_parts = display.split()
        log_label = display_parts[2] if len(display_parts) > 2 else display_parts[1]
        log_name = f"{index:02d}_{log_label}.log"
        log_name = log_name.replace("--", "").replace(".", "_")
        log_path = LOGS / log_name
        log_path.write_text(
            f"$ {display}\n[stdout]\n{result.stdout}\n[stderr]\n{result.stderr}",
            encoding="utf-8",
        )
        payload["commands"].append(
            {
                "command": display,
                "exit_code": result.returncode,
                "log": log_path.relative_to(AUDIT).as_posix(),
            }
        )
        _write_results(payload)
        print(f"[{result.returncode}] {display}")
    gate_path = AUDIT / "gate.json"
    if not gate_path.is_file():
        return 1
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    return 0 if gate.get("final_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
