"""Capture immutable Stage 1.6 pre-change metadata and regression evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BASELINE_COMMIT = "ec3250d7e3dba0379c3b5205949c23e4f4ee5d59"
ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 6),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_root", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "audit" / "stage1_6")
    args = parser.parse_args()
    baseline_root = args.baseline_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    baseline_head = _git(baseline_root, "rev-parse", "HEAD")
    if baseline_head != BASELINE_COMMIT:
        raise SystemExit(f"baseline HEAD mismatch: {baseline_head}")
    candidate_head = _git(ROOT, "rev-parse", "HEAD")
    candidate_branch = _git(ROOT, "branch", "--show-current")
    ancestor = (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, candidate_head],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )
    if not ancestor:
        raise SystemExit("baseline is not an ancestor of the candidate")

    tracked = _git(baseline_root, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    manifest_text = "\n".join(tracked) + "\n"
    lock_path = baseline_root / "uv.lock"
    prechange = {
        "schema_version": "1.0",
        "baseline_commit": baseline_head,
        "baseline_branch": _git(baseline_root, "branch", "--show-current") or "DETACHED",
        "baseline_dirty": bool(_git(baseline_root, "status", "--short")),
        "candidate_start_commit": candidate_head,
        "candidate_branch": candidate_branch,
        "baseline_is_candidate_ancestor": ancestor,
        "python_executable": sys.executable,
        "python_version": sys.version,
        "uv_version": os.environ.get("G2LC_UV_VERSION", "recorded by gate environment"),
        "lockfile_sha256": _sha256(lock_path),
        "tracked_file_count": len(tracked),
        "tracked_file_manifest": tracked,
        "tracked_file_manifest_sha256": hashlib.sha256(manifest_text.encode()).hexdigest(),
    }
    (output / "prechange.json").write_text(
        json.dumps(prechange, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(baseline_root / "src")
    probe = _run(
        [sys.executable, str(ROOT / "scripts" / "stage1_6_baseline_probe.py"), str(baseline_root)],
        cwd=baseline_root,
        env=env,
    )
    (output / "regressions_before.log").write_text(
        probe["stdout"] + probe["stderr"], encoding="utf-8"
    )
    try:
        parsed = json.loads(probe["stdout"])
    except json.JSONDecodeError:
        parsed = {"unparseable_stdout": probe["stdout"]}
    regression_evidence = {
        "schema_version": "1.0",
        "expected_probe_exit_code": 1,
        "probe": {key: value for key, value in probe.items() if key not in {"stdout", "stderr"}},
        "result": parsed,
    }
    (output / "regressions_before.json").write_text(
        json.dumps(regression_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if probe["exit_code"] == 1 and parsed.get("all_expected_defects_reproduced") else 1


if __name__ == "__main__":
    sys.exit(main())
