from __future__ import annotations

from pathlib import Path

import pytest

from g2lc.compiler.problem import LoadedCompilerProblem, load_compiler_problem

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def minimal_problem() -> LoadedCompilerProblem:
    return load_compiler_problem(ROOT / "examples/synthetic/minimal_dr/project.yaml")


@pytest.fixture(scope="session")
def missing_problem() -> LoadedCompilerProblem:
    return load_compiler_problem(ROOT / "examples/synthetic/missing_evidence/project.yaml")


@pytest.fixture(scope="session")
def oos_problem() -> LoadedCompilerProblem:
    return load_compiler_problem(ROOT / "examples/synthetic/out_of_spec/project.yaml")
