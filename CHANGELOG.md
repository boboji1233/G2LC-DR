# Changelog

All notable changes follow Keep a Changelog conventions. The project has not yet
made any clinical-validation or experiment-result claim.

## [Unreleased]

### Added

- Initial research-reproducible repository governance, task mapping, runbook, claim
  contract, data-access boundaries and architecture ADRs.
- Strict evidence ontology, typed guideline DSL, strong Kleene semantics, operator
  catalogue, observation partitions, derivation DAG and cost model.
- CP-SAT exact solver, brute-force oracle, deterministic greedy solver, Z3
  counterexample-separation solver, dominance analysis and minimum repair analysis.
- Deterministic EXECUTABLE/INCOMPLETE/OUT_OF_SPEC certificates and independent source,
  semantic-hash, Z3 and brute-force verification.
- Minimal, missing-evidence and out-of-specification synthetic fixtures plus the full CLI.
- Python 3.11 `uv` lock, ruff/mypy/pytest/Hypothesis quality gate, pre-commit, Makefile and
  GitHub Actions CI.
- Metadata-only local adapters, Parquet manifests, source-family warnings, SHA-256 audit
  and an audited immutable split-lock mechanism after Stage 1 passed.
- 86 tests with 89.47% scoped core coverage.
