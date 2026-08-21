# Project Status

Last updated: 2026-08-21 (Asia/Shanghai)

Stage 1.6 cross-path hardening is semantically frozen. Stage 1.6.1 adds packaging and
audit-finalization hygiene without changing guideline, solver, repair, certificate, or
independent-verifier semantics; its commit-bound dual-Python gate is authoritative.
Stage 2, Oracle, and visual training remain frozen.

## Current Stage 1.6 scope

- The work starts from verified commit `ec3250d7e3dba0379c3b5205949c23e4f4ee5d59`
  on `codex/stage1-6-cross-path-hardening`.
- Seven focused tests reproduced the audited residual defects before fixes; the
  regression ledger is `artifacts/audit/stage1_6/regressions_before.json`.
- Greedy selection now closes and pays prerequisites, finite conflict validation uses
  feasibility and derivation semantics, empty evidence languages fail closed, partial
  evaluation requires an explicit decision context and projects unrelated dimensions,
  and repair uses CP-SAT with a bounded brute-force oracle.
- Deterministic semantic generation varies Boolean/integer/categorical predicates,
  guidelines, all seven feasibility kinds, transitive unary derivations, prerequisite
  graphs, and Decimal objectives; failures persist by seed.
- Certificates now prove non-vacuity, bind the relevant-predicate closure, use
  action-distinction terminology, and are checked by the import-isolated verifier.
- Python 3.11/3.12 commands, coverage against 92/86 whole-project and 96/91 core
  line/branch floors, 200-case semantic results, tamper results, and bundle verification
  are reported only from `artifacts/audit/stage1_6/gate.json`.
- Stage 1.6.1 uses an explicit Hatch sdist allowlist, audits wheel/sdist contents and
  size, clean-installs both archives, and runs the installed CLI/version/minimal fixture.
  Build outputs are isolated under ignored audit paths, so repeated builds cannot ingest
  prior `dist/`, virtual environments, audit bundles, logs, or medical-data directories.
- A review archive embeds `EXTERNALIZED` for its impossible self-checksum. Its sibling
  `.sha256` and `_final_metadata.json` are the joint checksum authority; archive-only
  path normalization leaves raw command evidence unchanged on disk.

## Current Stage 1.5 audit

- The repository remains a functional prototype; the current Stage-1.5 synthetic
  semantic gate is `PASS`, without making a clinical or real-data claim.
- The prompt-mandated source audit confirmed unsound trace-sensitive decision signatures,
  incomplete priority semantics, untyped states, an unconstrained Cartesian state universe,
  structural-only derivations, unenforced operator prerequisites, rounded objectives,
  non-incremental repair accounting, and a verifier coupled to compiler internals.
- Final gate evidence: 188 tests, 0 failures; whole line/branch coverage
  92.4229%/85.6073%; core line/branch coverage 96.2706%/90.1015%; 20/20 seeded
  finite/brute-force/separation cases; 66/66 valid finite/Z3 schemes; 45/45 rehashed
  tamper cases rejected; package build and verifier import boundary passed.
- Detailed hypotheses, reproductions, fixes, and residual risks are tracked in
  `AUDIT_REPORT_STAGE1_5.md` and `THEORY_TO_TEST_MATRIX.md`.

Stage 1.5 proves decision sufficiency only under the declared finite evidence,
feasibility, derivation, modality, and guideline semantics.

## Completed in Stage 1.5

- Action-only decision semantics, finite/SMT feasibility, deterministic unary derivations,
  prerequisites, exact objectives, incremental repairs, independent three-outcome
  verification, non-enumerating SMT-universal certificates, tamper rejection,
  branch-aware gates, and the privacy-safe review bundle.

## Blocked

- No real medical dataset, expert label table or checkpoint has been supplied. Therefore
  no real manifest, Oracle result, metric, clinical rule validation or experiment result
  exists or is claimed.
- Official acquisition actions: request MESSIDOR-1 from ADCIS; sign/request FGADR Seg-set;
  request Retinal-Lesions through its official form; recheck current licenses before any
  explicit DDR/MMRDR/IDRiD/DeepDRiD/MAPLES-label download. See `docs/data_access_log.md`.
- Production MESSIDOR/Canadian/ICDR/NHS rules remain blocked on official clause-by-clause
  transcription and clinical review. Synthetic rules are not substitutes.
- Experiment registry/model/baseline scaffolding remains gated on verified dataset
  adapters, deduplication, immutable split manifests and the Oracle Go/No-Go gate.

## Next dependency-satisfied tasks

1. Review `artifacts/audit/stage1_6/gate.json`, the Stage-1.6.1 commit-addressed bundle,
   its external checksum/final metadata, and `OWNER_ACTIONS_AFTER_STAGE1_6.md`.
2. Keep all Stage 2, real-data parsing, Oracle, and visual-model work frozen until a
   separately authorized task satisfies its own data, provenance, and scientific gates.

## Commands and exact outcomes

The authoritative command ledger for this audit is generated under
`artifacts/audit/stage1_6/`. Documentation never substitutes copied console text for the
machine-readable, commit-bound gate.
