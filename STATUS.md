# Project Status

Last updated: 2026-08-20 (Asia/Shanghai)

Stage 1 functional prototype exists.
Stage 1.5 semantic soundness gate is PASS in this checkout.
Stage 2, Oracle, and visual training are frozen.

## Current Stage 1.5 audit

- The repository remains a functional prototype; the current Stage-1.5 synthetic
  semantic gate is `PASS`, without making a clinical or real-data claim.
- The prompt-mandated source audit confirmed unsound trace-sensitive decision signatures,
  incomplete priority semantics, untyped states, an unconstrained Cartesian state universe,
  structural-only derivations, unenforced operator prerequisites, rounded objectives,
  non-incremental repair accounting, and a verifier coupled to compiler internals.
- The local Git repository has no `HEAD`; all files are currently untracked. The requested
  baseline commit therefore cannot be verified in this checkout and will not be fabricated.
- The first untouched test attempt, `uv run pytest -q`, exited 1 because `uv` is not on this
  host's `PATH`. This is an environment failure, not a passing or failing test suite.
- A temporary, pinned `uv 0.12.5` executable was installed under the host temporary
  directory. The portable runner then completed every mandatory command with exit 0.
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

1. Review `artifacts/audit/stage1_5/gate.json` and the checksum-addressed Stage-1.5 bundle.
2. Keep all Stage 2, real-data parsing, Oracle, and visual-model work frozen until a
   separately authorized task satisfies its own data, provenance, and scientific gates.

## Commands and exact outcomes

The authoritative command ledger for this audit is generated under
`artifacts/audit/stage1_5/`. Historical results formerly listed here are not treated as
Stage 1.5 evidence because they were produced before the semantic contract was corrected.
The final gate status is `PASS`; the repository has no commit/`HEAD`, so this result is
bound to the recorded dirty checkout and fixture hashes rather than a fabricated commit.
