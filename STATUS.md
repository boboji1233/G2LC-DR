# Project Status

Last updated: 2026-08-21 (Asia/Shanghai)

Stage 1.6.1 is semantically frozen and remains a mandatory prerequisite. Stage 2A now
implements provenance-safe medical-data governance and Oracle-input readiness only.
Oracle execution, guideline replay on real labels, visual models, training, checkpoints,
and experiments remain frozen. The dual-Python, commit-bound Stage 2A gate is authoritative.

## Current Stage 2A scope

- Six schema-v2 relations (`cases`, `images`, `labels`, `regions`, `correspondences`,
  `splits`) use deterministic global IDs, row hashes, source hashes, and provenance.
- Label status distinguishes positive, negative, unknown, ambiguous, not-applicable,
  weak, and derived evidence; migration tests prove missing labels stay `UNKNOWN`.
- Ten local-only adapters expose five explicit readiness states. They download nothing,
  accept no terms, guess no source columns, and parse zero clinical labels without
  legally supplied official source files.
- The public versioned access ledger records only official facts and owner actions.
- Source-family policy fixes DDR/MMRDR-CFP as `OIA_DDR` and MESSIDOR/MAPLES as
  `MESSIDOR1`. MAPLES-corresponding cases are locked final same-case tests and cannot
  enter any selection, calibration, validation, or training use.
- Exact-file, decoded-pixel, pHash, and dHash evidence is deterministic and
  source-family aware. Perceptual matches require review; automatic deletion is disabled
  and embedding-based deduplication is `NOT_RUN`.
- The portable gate runs Stage 1.6.1 first, quality and adversarial tests on Python
  3.11/3.12, forbidden-content scans, build/package audits, and review verification.
- Starting identity and prerequisite evidence are recorded in `docs/stage2a_baseline.md`;
  architectural policy is ADR-0006.

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

## Blocked beyond Stage 2A

- No real medical dataset, expert label table or checkpoint has been supplied. Therefore
  no real manifest, Oracle result, metric, clinical rule validation or experiment result
  exists or is claimed.
- Official acquisition actions: request MESSIDOR-1 from ADCIS; sign/request FGADR Seg-set;
  request Retinal-Lesions through its official form; recheck current licenses before any
  explicit DDR/MMRDR/IDRiD/DeepDRiD/MAPLES-label download. See `docs/data_access_log.md`.
- Production MESSIDOR/Canadian/ICDR/NHS rules remain blocked on official clause-by-clause
  transcription and clinical review. Synthetic rules are not substitutes.
- Source-specific label parsing remains blocked until legally supplied official files can
  be inspected and tested without guessing schemas.
- Experiment registry/model/baseline scaffolding remains gated on ready adapters,
  reviewed duplicate groups, immutable split manifests, and the Oracle Go/No-Go gate.

## Next dependency-satisfied tasks

1. Review `artifacts/audit/stage2a/gate.json`, the commit-addressed Stage 2A bundle, its
   external checksum/final metadata, ADR-0006, and the public access ledger.
2. Owner-only acquisition actions may be completed outside Git. Re-run `data status` and
   adapter inspection after each legally supplied local dataset is available.
3. Keep Oracle execution and all visual-model work frozen until the separate Oracle
   input gate has ready, deduplicated, immutable legal inputs.

## Commands and exact outcomes

The Stage 1.6 prerequisite ledger remains under `artifacts/audit/stage1_6/`; Stage 2A
evidence is generated under `artifacts/audit/stage2a/`. Documentation never substitutes
copied console text for either machine-readable, commit-bound gate.
