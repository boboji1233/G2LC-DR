# G2LC-DR Stage 1.6 Audit Report

Date: 2026-08-20

Baseline: `ec3250d7e3dba0379c3b5205949c23e4f4ee5d59`

Scope: synthetic compiler semantics only

## Reproduction

The pre-change ledger records a clean verified baseline. Seven focused regression tests
then failed: greedy prerequisite selection/cost, finite/SMT feasibility conflict parity,
three empty-language solver paths, partial evaluation with derivation, and typed identity
derived equality. The exact commands and exit codes are retained under
`artifacts/audit/stage1_6/`; generated semantic failures are persisted by seed under
`tests/fixtures/regressions/generated/`.

## Corrections

- One defensive prerequisite-closure function is shared by solvers, repair, certificates,
  and audits; greedy scores incremental closure benefit/cost and validates its result.
- Guideline conflict checking applies feasibility and derivations in finite and SMT modes.
- Z3 produces a canonical evidence-language witness; all compiler paths and the independent
  verifier reject an empty language.
- Partial evidence completions are derivation-consistent.
- Relevant-state projection preserves a witness completion and is checked against full
  finite optimization.
- Repair uses CP-SAT with exact Decimal lexicographic objectives and a bounded brute oracle.
- Certificate fields bind non-vacuity and relevant closure; 54 substantive rehashed
  mutations are independently rejected.

## Acceptance and limitations

The final command results, Python 3.11/3.12 coverage, 200-case semantic matrix, build,
tamper matrix, bundle verification, commit, and final verdict live only in
`artifacts/audit/stage1_6/gate.json`. This report does not predeclare those results.

Remaining deliberate limits are deterministic unary total derivations, finite declared
domains, bounded independent optimum/repair oracles, and synthetic fixtures. No clinical
rule, label, dataset, metric, Oracle result, or visual model was created or inferred.
