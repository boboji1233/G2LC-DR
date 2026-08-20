# Project Status

Last updated: 2026-08-20 (Asia/Shanghai)

## Completed

### Stage 1 compiler gate

- Read the authoritative v1.0 research plan in full (4,034 physical lines), initialized
  Git, and mapped modules to A/C/D/P0 task IDs in `IMPLEMENTATION_PLAN.md`.
- Added Python 3.11/`uv` tooling, a locked environment, ruff, mypy, pytest/Hypothesis,
  pre-commit, Make targets and GitHub Actions CI.
- Implemented strict ontology, evidence-state, guideline AST, clause provenance,
  three-valued evaluator, annotation operators, coarsened observations, derivation DAG,
  compiler problem/solution and three certificate models.
- Implemented finite CP-SAT exact compilation, brute-force oracle, deterministic greedy
  compilation, safe dominance detection, Z3 counterexample search and restricted-master
  counterexample separation.
- Implemented canonical deterministic certificate JSON and an independent verifier that
  reloads sources, checks byte/semantic hashes, checks Z3 executability and checks finite
  exact optimality/repair with brute force.
- Added three explicitly synthetic fixtures. Fixture A has known optimum
  `{quality_label, ma_presence_label, hem_count_bin_label, nv_presence_label}` at relative
  development cost `5.0`. Fixture B returns exactly missing `nv_presence` and repair
  `nv_presence_label` at cost `1.5`. Fixture C rejects `oct_central_thickness` for CFP and
  reports required modality `OCT`.
- Added required validation/evaluation/compile/certificate/synthetic/status/data CLI
  command groups, README, runbook, claim contract, access log and architecture ADRs.
- Added 56 focused unit tests, 13 guideline semantic tests, 12 Hypothesis property tests
  and 5 CLI integration tests (86 total).

### Metadata-only data safeguards (started only after Stage 1 passed)

- Added local-path-only inventory adapters for DDR, MMRDR-CFP, MMRDR-UWF, IDRiD,
  DeepDRiD, FGADR, MAPLES/MESSIDOR and Retinal-Lesions.
- Added unified Parquet metadata, image SHA-256, explicit license confirmation, dry-run
  audit, `UNKNOWN` default labels, OIA-DDR/EyePACS overlap warnings and MAPLES test-lock
  metadata.
- Added deterministic patient-assignment split locks. A changed lock requires an explicit
  dangerous override, a reason and an append-only JSONL audit event.

## In progress

- Dataset-specific official label-table parsing is not started because no legal source
  files are present. The current adapters intentionally do not infer labels from names.
- Duplicate audit currently implements exact SHA-256. Perceptual-hash candidates,
  optional embedding nearest neighbours, optional SSIM confirmation and human-review CSV
  remain later F-01 work.

## Blocked

- No real medical dataset, expert label table or checkpoint has been supplied. Therefore
  no real manifest, Oracle result, metric, clinical rule validation or experiment result
  exists or is claimed.
- Official acquisition actions: request MESSIDOR-1 from ADCIS; sign/request FGADR Seg-set;
  request Retinal-Lesions through its official form; recheck current licenses before any
  explicit DDR/MMRDR/IDRiD/DeepDRiD/MAPLES-label download. See `docs/data_access_log.md`.
- Production MESSIDOR/Canadian/ICDR/NHS rules remain blocked on official clause-by-clause
  transcription and clinical review. Synthetic rules are not substitutes.
- `make` is not installed on this Windows host. The Makefile targets map to commands that
  passed directly; GitHub Actions runs the portable Linux environment.
- Experiment registry/model/baseline scaffolding remains gated on verified dataset
  adapters, deduplication, immutable split manifests and the Oracle Go/No-Go gate.

## Next dependency-satisfied tasks

1. With a legally supplied dataset, inspect only its official metadata schema and add a
   source-specific parser that preserves raw values/provenance and missing=`UNKNOWN`.
2. Complete pHash/embedding/SSIM duplicate candidate stages and a human-review CSV.
3. Freeze and test the MAPLES/MESSIDOR 198-case match and split hash before opening target
   labels for evaluation.
4. Transcribe one official guideline only with source/section/version/review metadata and
   boundary tests; do not promote draft rules without clinical review.
5. Run Oracle Gate E before creating any visual training or experiment claim.

## Commands and exact outcomes

| Command | Outcome |
|---|---|
| Chunked full read of `G2LC_DR_KBS_Research_Plan_CN.md` | PASS; all 4,034 lines read |
| `git init` | PASS |
| `uv sync --locked --all-groups` | PASS; 47 packages resolved/checked from `uv.lock` |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS; 76 files formatted |
| `uv run mypy src` | PASS; 48 source files, zero issues |
| `uv run pytest -q` | PASS; 86 tests |
| `uv run pytest -q --cov=g2lc --cov-report=term-missing --cov-fail-under=85` | PASS; 89.47% scoped core coverage |
| `uv run g2lc synthetic run --fixture minimal_dr` | PASS; `OPTIMAL`, four operators, cost 5.0 |
| `uv run g2lc certificate verify artifacts/synthetic/minimal_dr/certificate.json` | PASS; hashes, cost, derivations, Z3 and brute-force optimum |
| Greedy minimal fixture + verifier | PASS; feasible cost 5.8, independently executable |
| Z3 separation minimal fixture + verifier | PASS; optimal cost 5.0, no counterexample |
| Missing-evidence fixture + verifier | PASS; exact predicate/operator repair recovered |
| OOS fixture + verifier | PASS; OCT predicate/modality/source clause recovered |

Generated certificates are reproducible workspace artifacts and intentionally ignored by
Git; rerun the synthetic command before verification in a clean checkout.
