# Changelog

All notable changes follow Keep a Changelog conventions. The project has not yet
made any clinical-validation or experiment-result claim.

## [Unreleased]

### Stage 1.6.1 packaging hygiene

- Replaced implicit sdist discovery with an explicit Hatch include/exclude policy and
  broadened local ignores to cover `.venv*`, build caches, logs, checkpoints, review
  bundles, generated outputs, and raw/interim/processed medical-data roots.
- Added wheel (<2 MiB) and sdist (<5 MiB) content audits, forbidden-member/secret/local-
  path scans, clean isolated installs of both archives, installed-version checks, and an
  installed minimal synthetic CLI smoke test.
- Isolated every build in a run-specific ignored audit directory and compare archive
  member sets across Python 3.11 and 3.12, preventing recursive inclusion of earlier
  `dist/` or build outputs.
- Externalized the review archive's recursive SHA-256: embedded gates say
  `EXTERNALIZED`, while the sibling `.sha256` and `_final_metadata.json` carry the final
  authoritative digest. Review exports normalize local paths without mutating raw logs.
- Stage 1.6 decision, feasibility, derivation, objective, repair, certificate, and
  independent-verifier semantics remain unchanged; Stage 2 remains frozen.

### Stage 1.6 cross-path hardening

- Fixed Python 3.12 mypy targeting by allowing the active interpreter to select syntax.
- Made greedy and dominance prerequisite-closure aware, with closure cost charged once.
- Unified finite conflict, explicit-context partial evaluation, finite enumeration, Z3,
  and independent verification around feasibility, deterministic derivation, and
  nonempty-language rules; legacy calls that omit derivations now fail loudly.
- Added decision-relevant state projection, CP-SAT incremental repair with a bounded
  brute-force oracle, and fail-closed symbolic repair limits.
- Added 200 generated semantic problems varying Boolean/integer/categorical domains,
  guideline priorities/defaults, all seven feasibility kinds, transitive unary
  derivations, prerequisite DAGs, and exact Decimal objectives; added 54 rehashed tamper
  cases, dual-Python CI, and a commit-bound verified bundle.
- Added an immutable-baseline reproduction probe and machine-readable pre-change ledger,
  plus strict 92/86 whole-project and 96/91 core line/branch coverage thresholds.
- Added certificate non-vacuity and relevant-closure evidence and replaced misleading
  clause-coverage naming with decision-program/action-distinction provenance.
- Stage 2, real-data parsing, Oracle experiments, and visual-model work remain frozen.

### Stage 1.5 semantic soundness

- Replaced trace-sensitive equivalence with one action-only decision signature shared by
  Python evaluation, finite CP-SAT, brute force, Z3 separation, repair, and independent
  certificate verification.
- Added feasible-completion semantics for partial evidence, typed scalar identity, a
  versioned feasibility DSL, deterministic unary total derivations, and enforced
  operator/evidence/modality prerequisites.
- Replaced rounded objectives with exact decimal cost/count/operator-ID ordering and
  changed repair to minimum incremental unavailable additions relative to all available
  base evidence.
- Added certificate schema 1.1, the import-isolated `g2lc_verifier`, three-outcome
  source recomputation, and a rehashed substantive-field tamper matrix.
- Added the explicit synthetic Stage-1.5 fixture manifest, finite/brute-force/Z3 seeded
  differential matrix, branch coverage thresholds, portable audit runner, CI matrix,
  and privacy-safe review bundle.
- Added ADR-0003 and the audit/theory-to-test reports. Real-data parsing, Oracle
  experiments, and visual-model work were not started.
- Final current-checkout gate: PASS with 188 tests and 0 failures; exact coverage,
  equivalence, tamper, build, environment, and artifact hashes remain in `gate.json`.

Stage 1.5 proves decision sufficiency only under the declared finite evidence,
feasibility, derivation, modality, and guideline semantics.

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
- Test counts, line/branch coverage, solver-equivalence results, tamper results, and the
  final gate outcome are machine-recorded in `artifacts/audit/stage1_5/gate.json` rather
  than copied as pre-gate claims.
